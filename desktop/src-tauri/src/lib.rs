use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WebviewWindow,
};
use tauri_plugin_updater::UpdaterExt;

struct BackendProcess(Mutex<Option<Child>>);

/// Resolve the Python executable and app directory.
///
/// In debug builds: uses the project's `app/.venv/bin/python3` and `app/` directory.
/// In release builds: resolves paths relative to the .app bundle's `Resources/backend/`.
fn backend_paths() -> (PathBuf, PathBuf) {
    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let project_root = manifest_dir.parent().unwrap().parent().unwrap().to_path_buf();
        let python = project_root.join("app/.venv/bin/python3");
        let app_dir = project_root.join("app");
        (python, app_dir)
    } else {
        // Release: resolve relative to the .app bundle
        // current_exe() → /Applications/KI.app/Contents/MacOS/knowledge-intelligence
        // parent()      → Contents/MacOS
        // parent()      → Contents
        // Resources/backend/python/bin/python3
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_else(|| PathBuf::from("."));
        let contents = exe_dir.parent().unwrap().to_path_buf();
        let resources = contents.join("Resources");
        let backend_root = resources.join("backend");
        let python = backend_root.join("python/bin/python3");
        let app_dir = backend_root.clone();
        (python, app_dir)
    }
}

/// Resolve KI_HOME (data directory). Uses ~/Documents/KI/ in release,
/// falls back to the app_dir parent in debug.
fn dirs_next(app_dir: &PathBuf) -> PathBuf {
    if cfg!(debug_assertions) {
        app_dir.join("../data")
    } else {
        let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
        home.join("Documents/KI")
    }
}

/// Escape a string for safe injection into a JS single-quoted string inside eval().
fn js_escape(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

/// Show a formatted error box on the splash screen.
fn show_splash_error(splash: &WebviewWindow, title: &str, detail: &str) {
    let title_esc = js_escape(title);
    let detail_esc = js_escape(detail);
    let js = format!(
        r#"(function(){{
            var sub = document.querySelector('.subtitle');
            if(sub) sub.textContent = '{}';
            var loader = document.querySelector('.loader');
            if(loader) loader.style.display = 'none';
            var existing = document.querySelector('.error-box');
            if(existing) existing.remove();
            var d = document.createElement('div');
            d.className = 'error-box';
            d.style.cssText = 'margin-top:16px;font-size:11px;color:#ef4444;max-width:300px;word-break:break-all;line-height:1.5;text-align:left;padding:10px 12px;background:#1a1a2e;border-radius:8px;border:1px solid #3b1c1c;white-space:pre-wrap;max-height:140px;overflow-y:auto;font-family:ui-monospace,SFMono-Regular,monospace';
            d.textContent = '{}';
            document.querySelector('.container').appendChild(d);
        }})()"#,
        title_esc, detail_esc
    );
    let _ = splash.eval(&js);
}

/// Spawn a background task to check for updates.
/// Runs silently — if an update is found, downloads, installs, and restarts.
fn spawn_update_check(handle: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        eprintln!("[ki-updater] Checking for updates...");

        let updater = match handle.updater() {
            Ok(u) => u,
            Err(e) => {
                eprintln!("[ki-updater] Updater init failed: {}", e);
                return;
            }
        };

        let update = match updater.check().await {
            Ok(Some(u)) => u,
            Ok(None) => {
                eprintln!("[ki-updater] Already up to date");
                return;
            }
            Err(e) => {
                eprintln!("[ki-updater] Check failed (network/endpoint): {}", e);
                return;
            }
        };

        eprintln!(
            "[ki-updater] Update found: current → v{}",
            update.version
        );

        match update
            .download_and_install(
                |chunk_length, content_length| {
                    if let Some(total) = content_length {
                        let pct = if total > 0 {
                            (chunk_length as f64 / total as f64 * 100.0) as u32
                        } else {
                            0
                        };
                        eprintln!("[ki-updater] Download: {}%", pct);
                    }
                },
                || {
                    eprintln!("[ki-updater] Download complete, installing...");
                },
            )
            .await
        {
            Ok(()) => {
                eprintln!("[ki-updater] Update installed, restarting...");
                handle.restart();
            }
            Err(e) => {
                eprintln!("[ki-updater] Install failed: {}", e);
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            let (venv_python, app_dir) = backend_paths();

            // --- Splash screen ---
            let splash_url = if cfg!(debug_assertions) {
                tauri::WebviewUrl::External(
                    "http://127.0.0.1:5173/splash.html".parse().unwrap(),
                )
            } else {
                tauri::WebviewUrl::App("splash.html".into())
            };

            let splash = tauri::WebviewWindowBuilder::new(app, "splash", splash_url)
                .title("Knowledge Intelligence")
                .inner_size(360.0, 280.0)
                .resizable(false)
                .decorations(false)
                .always_on_top(true)
                .center()
                .build()?;

            // --- Kill stale backend ---
            let _ = Command::new("lsof")
                .args(["-ti", ":9120"])
                .output()
                .ok()
                .and_then(|o| {
                    if o.status.success() && !o.stdout.is_empty() {
                        let pids = String::from_utf8_lossy(&o.stdout);
                        eprintln!(
                            "[ki-setup] Stale backend PIDs on :9120 — killing: {}",
                            pids.trim()
                        );
                        let _ = Command::new("kill")
                            .args(["-9"])
                            .args(pids.split_whitespace())
                            .output();
                    }
                    Some(())
                });
            std::thread::sleep(Duration::from_millis(500));

            eprintln!(
                "[ki-setup] Python: {:?}  cwd: {:?}",
                venv_python, app_dir
            );

            // --- Spawn Python backend ---
            let python_home = app_dir.join("python");
            let ki_home = dirs_next(&app_dir);
            let child = Command::new(&venv_python)
                .args([
                    "-m", "uvicorn", "backend.main:app",
                    "--host", "127.0.0.1", "--port", "9120",
                ])
                .current_dir(&app_dir)
                .env("PYTHONHOME", &python_home)
                .env("VIRTUAL_ENV", &python_home)
                .env("KI_HOME", &ki_home)
                .env("KI_TAURI", "1")
                .env("PATH", format!("{}:{}",
                    python_home.join("bin").display(),
                    std::env::var("PATH").unwrap_or_default()))
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn();

            let backend_ok = match child {
                Ok(mut child) => {
                    // Wait longer on first launch — Rosetta 2 translation can be slow
                    std::thread::sleep(Duration::from_secs(8));
                    match child.try_wait() {
                        Ok(Some(status)) => {
                            // Backend died — collect full diagnostics
                            let mut stderr_out = String::new();
                            let mut stdout_out = String::new();
                            if let Some(ref mut s) = child.stderr {
                                use std::io::Read;
                                let _ = s.read_to_string(&mut stderr_out);
                            }
                            if let Some(ref mut s) = child.stdout {
                                use std::io::Read;
                                let _ = s.read_to_string(&mut stdout_out);
                            }
                            let exit_code = status.code().map(|c| c.to_string()).unwrap_or_else(|| "signal".into());
                            eprintln!(
                                "[ki-setup] ❌ BACKEND DIED (exit {})\n\
                                 Python: {:?}\n\
                                 cwd: {:?}\n\
                                 PYTHONHOME: {:?}\n\
                                 stdout: {}\n\
                                 stderr: {}",
                                exit_code, venv_python, app_dir, python_home, stdout_out, stderr_out
                            );

                            // Show diagnostic info on splash
                            let detail = if stderr_out.is_empty() && stdout_out.is_empty() {
                                format!("进程异常退出 (exit {})\nPython: {:?}\n请检查依赖是否完整", exit_code, venv_python)
                            } else {
                                // Show last 500 chars of combined output
                                let combined = format!("stdout:\n{}\nstderr:\n{}", stdout_out, stderr_out);
                                let tail: String = if combined.len() > 500 {
                                    format!("...\n{}", combined.chars().rev().take(500).collect::<String>().chars().rev().collect::<String>())
                                } else {
                                    combined
                                };
                                format!("进程异常退出 (exit {})\n{}", exit_code, tail)
                            };
                            show_splash_error(&splash, "启动失败 — 后端进程异常退出", &detail);
                            false
                        }
                        Ok(None) => {
                            app.manage(BackendProcess(Mutex::new(Some(child))));
                            eprintln!("[ki-setup] ✅ Backend running on http://127.0.0.1:9120");
                            true
                        }
                        Err(e) => {
                            eprintln!("[ki-setup] try_wait error: {}", e);
                            show_splash_error(&splash, "启动失败 — 进程状态异常", &e.to_string());
                            false
                        }
                    }
                }
                Err(e) => {
                    let err_str = e.to_string();
                    eprintln!(
                        "[ki-setup] ❌ Failed to spawn backend\n\
                         Python: {:?}\n\
                         Error: {}\n\
                         Does the Python binary exist? {:?}",
                        venv_python, err_str, venv_python.exists()
                    );

                    // Build diagnostic message
                    let mut detail = format!("无法启动 Python 后端\n{}", err_str);

                    // Check for Rosetta 2 hint
                    if err_str.contains("bad CPU") || err_str.contains("Bad CPU") || err_str.contains("EBADARCH") {
                        detail.push_str("\n\n可能需要 Rosetta 2：\nsoftwareupdate --install-rosetta");
                    }
                    // Check if Python binary missing
                    if !venv_python.exists() {
                        detail.push_str(&format!("\n\nPython 二进制不存在:\n{:?}", venv_python));
                    }

                    show_splash_error(&splash, "启动失败 — 无法启动后端", &detail);
                    false
                }
            };

            if backend_ok {
                // Spawn background update check (non-blocking, silent)
                spawn_update_check(app.handle().clone());

                splash.close()?;
                if let Some(main) = app.get_webview_window("main") {
                    main.show()?;
                    main.set_focus()?;
                }

                // --- System tray ---
                let icon = app.default_window_icon().cloned().unwrap();
                let toggle = MenuItemBuilder::with_id("toggle", "显示/隐藏").build(app)?;
                let quit = MenuItemBuilder::with_id("quit", "退出").build(app)?;
                let menu = MenuBuilder::new(app).items(&[&toggle, &quit]).build()?;

                let _tray = TrayIconBuilder::new()
                    .icon(icon)
                    .menu(&menu)
                    .tooltip("Knowledge Intelligence")
                    .on_menu_event(|app, event| match event.id().as_ref() {
                        "toggle" => {
                            if let Some(w) = app.get_webview_window("main") {
                                if w.is_visible().unwrap_or(false) {
                                    w.hide().ok();
                                } else {
                                    w.show().ok();
                                    w.set_focus().ok();
                                }
                            }
                        }
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    })
                    .on_tray_icon_event(|tray, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            let app = tray.app_handle();
                            if let Some(w) = app.get_webview_window("main") {
                                if w.is_visible().unwrap_or(false) {
                                    w.hide().ok();
                                } else {
                                    w.show().ok();
                                    w.set_focus().ok();
                                }
                            }
                        }
                    })
                    .build(app)?;

                // --- Global shortcut: Cmd+K ---
                use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
                let shortcut = Shortcut::new(Some(Modifiers::SUPER), Code::KeyK);
                let _ = app.global_shortcut().register(shortcut);
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            if let Some(state) = app_handle.try_state::<BackendProcess>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(ref mut child) = *guard {
                        let _ = child.kill();
                    }
                }
            }
        }
    });
}
