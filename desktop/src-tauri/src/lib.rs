use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

struct BackendProcess(Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
            let project_root = manifest_dir.parent().unwrap().parent().unwrap().to_path_buf();
            let venv_python = project_root.join("app/.venv/bin/python3");
            let app_dir = project_root.join("app");

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

            // --- Spawn Python backend ---
            let child = Command::new(&venv_python)
                .args([
                    "-m", "uvicorn", "backend.main:app",
                    "--host", "127.0.0.1", "--port", "9120",
                ])
                .current_dir(&app_dir)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn();

            let backend_ok = match child {
                Ok(mut child) => {
                    std::thread::sleep(Duration::from_secs(2));
                    match child.try_wait() {
                        Ok(Some(status)) => {
                            let mut stderr = String::new();
                            if let Some(ref mut s) = child.stderr {
                                use std::io::Read;
                                let _ = s.read_to_string(&mut stderr);
                            }
                            eprintln!(
                                "[ki-setup] BACKEND DIED: {:?}\nstderr: {}",
                                status, stderr
                            );
                            let _ = splash.eval(
                                r#"document.querySelector('.subtitle').textContent='启动失败，请检查日志';document.querySelector('.loader').style.display='none'"#,
                            );
                            false
                        }
                        Ok(None) => {
                            app.manage(BackendProcess(Mutex::new(Some(child))));
                            eprintln!("[ki-setup] ✅ Backend running on http://127.0.0.1:9120");
                            true
                        }
                        Err(e) => {
                            eprintln!("[ki-setup] try_wait error: {}", e);
                            false
                        }
                    }
                }
                Err(e) => {
                    eprintln!("[ki-setup] ❌ Failed to spawn backend: {}", e);
                    let _ = splash.eval(
                        r#"document.querySelector('.subtitle').textContent='启动失败';document.querySelector('.loader').style.display='none'"#,
                    );
                    false
                }
            };

            if backend_ok {
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
