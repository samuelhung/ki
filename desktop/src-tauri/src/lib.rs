use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, WebviewWindow,
};
use tauri_plugin_updater::UpdaterExt;

struct BackendProcess(Mutex<Option<Child>>);

/// Tauri command: expose app version to frontend.
#[tauri::command]
fn get_desktop_version(app: tauri::AppHandle) -> String {
    app.package_info().version.to_string()
}

/// Tauri command: manually check for updates from frontend.
#[tauri::command]
async fn check_updates(app: tauri::AppHandle) -> Result<String, String> {
    let updater = match app.updater() {
        Ok(u) => u,
        Err(e) => {
            let msg = format!("初始化更新器失败: {}", e);
            eprintln!("[知几更新] {}", msg);
            return Err(msg);
        }
    };
    eprintln!("[知几更新] 手动检查更新... endpoint: {:?}", std::env::var("KI_DESKTOP_ENDPOINT"));
    match updater.check().await {
        Ok(Some(update)) => {
            let new_ver = update.version.clone();
            eprintln!("[知几更新] 发现新版本 v{}", new_ver);
            let app_handle = app.clone();
            tauri::async_runtime::spawn(async move {
                let app_handle1 = app_handle.clone();
                match update
                    .download_and_install(
                        {
                            let mut downloaded: u64 = 0;
                            move |chunk, total| {
                                downloaded += chunk as u64;
                                let (pct, msg) = if let Some(t) = total {
                                    let p = if t > 0 { (downloaded as f64 / t as f64 * 100.0) as u32 } else { 0 };
                                    (p, format!("下载中 {}%", p))
                                } else {
                                    let mb = downloaded as f64 / 1_048_576.0;
                                    (0, format!("下载中 {:.1} MB", mb))
                                };
                                let _ = app_handle1.emit("update-progress", serde_json::json!({
                                    "stage": "downloading",
                                    "percent": pct,
                                    "message": msg
                                }));
                            }
                        },
                        || {
                            let _ = app_handle.emit("update-progress", serde_json::json!({
                                "stage": "installing",
                                "percent": 100,
                                "message": "安装中..."
                            }));
                        },
                    )
                    .await
                {
                    Ok(()) => {
                        let _ = app_handle.emit("update-progress", serde_json::json!({
                            "stage": "done",
                            "percent": 100,
                            "message": "更新完成，即将重启"
                        }));
                        app_handle.restart();
                    }
                    Err(e) => {
                        let _ = app_handle.emit("update-progress", serde_json::json!({
                            "stage": "error",
                            "percent": 0,
                            "message": format!("安装失败: {}", e)
                        }));
                    }
                }
            });
            Ok(format!("v{}", new_ver))
        }
        Ok(None) => {
            eprintln!("[知几更新] 已是最新版本");
            Ok("latest".into())
        }
        Err(e) => {
            let msg = format!("检查失败: {}", e);
            eprintln!("[知几更新] {}", msg);
            Err(msg)
        }
    }
}

/// Tauri command: get latest crash log if any.
#[tauri::command]
fn get_crash_logs(_app: tauri::AppHandle) -> Vec<serde_json::Value> {
    let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    let crash_dir = home.join("Documents/KI/crashes");
    if !crash_dir.exists() {
        return vec![];
    }
    let mut logs = vec![];
    if let Ok(entries) = std::fs::read_dir(&crash_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map(|e| e == "log").unwrap_or(false) {
                if let Ok(content) = std::fs::read_to_string(&path) {
                    let name = path.file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_default();
                    logs.push(serde_json::json!({
                        "name": name,
                        "content": content.chars().take(2000).collect::<String>(),
                    }));
                }
            }
        }
    }
    logs.sort_by(|a, b| b["name"].as_str().cmp(&a["name"].as_str()));
    logs
}

/// Migrate data from old project directory to ~/Documents/KI/ on first launch.
fn migrate_data_if_needed(ki_home: &PathBuf) {
    let marker = ki_home.join(".migrated");
    if marker.exists() {
        return;
    }

    let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
    let old_data = home.join("Documents/Projects/KnowledgeIntelligence/data");
    let old_db = old_data.join("intelligence.sqlite");

    if old_db.exists() {
        let new_data = ki_home.join("data");
        let new_db = new_data.join("intelligence.sqlite");

        let should_migrate = !new_db.exists()
            || (old_db.metadata().map(|m| m.len()).unwrap_or(0)
                > new_db.metadata().map(|m| m.len()).unwrap_or(0)
                && new_db.metadata().map(|m| m.len()).unwrap_or(0) < 10_000_000);

        if should_migrate {
            eprintln!(
                "[知几] 迁移数据: {:?} → {:?}",
                old_db, new_db
            );
            let _ = std::fs::create_dir_all(&new_data);
            if let Err(e) = std::fs::copy(&old_db, &new_db) {
                eprintln!("[知几] 数据库迁移失败: {}", e);
            } else {
                eprintln!("[知几] ✅ 数据库已迁移 ({:.0} MB)",
                    old_db.metadata().map(|m| m.len()).unwrap_or(0) as f64 / 1_048_576.0);
            }

            for sub in &["audio", "videos", "summaries", "transcripts"] {
                let old_sub = old_data.join("ingest").join(sub);
                let new_sub = new_data.join("ingest").join(sub);
                if old_sub.exists() && !new_sub.exists() {
                    let _ = std::fs::create_dir_all(new_sub.parent().unwrap_or(&new_sub));
                    let _ = Command::new("cp")
                        .args(["-R", &old_sub.to_string_lossy(), &new_sub.to_string_lossy()])
                        .output();
                }
            }
        }
    }

    let _ = std::fs::write(&marker, "migrated");
}

/// Resolve Python executable and app directory.
fn backend_paths() -> (PathBuf, PathBuf) {
    if cfg!(debug_assertions) {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let project_root = manifest_dir.parent().unwrap().parent().unwrap().to_path_buf();
        let python = project_root.join("app/.venv/bin/python3");
        let app_dir = project_root.join("app");
        (python, app_dir)
    } else {
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

/// Resolve KI_HOME (data directory).
fn dirs_next(app_dir: &PathBuf) -> PathBuf {
    if cfg!(debug_assertions) {
        app_dir.join("../data")
    } else {
        let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("."));
        home.join("Documents/KI")
    }
}

/// Escape string for JS injection.
fn js_escape(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

/// Show error on splash screen.
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

/// Save backend crash log to ~/Documents/KI/crashes/
fn save_crash_log(ki_home: &PathBuf, stderr: &str, _exit_code: &str) {
    let crash_dir = ki_home.join("crashes");
    let _ = std::fs::create_dir_all(&crash_dir);
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_else(|_| "unknown".into());
    let path = crash_dir.join(format!("backend_crash_{}.log", ts));
    let _ = std::fs::write(&path, stderr);
    eprintln!("[知几] 崩溃日志已保存: {:?}", path);
}

/// Spawn background update check with progress events.
fn spawn_update_check(handle: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        eprintln!("[知几更新] 后台检查更新...");

        let updater = match handle.updater() {
            Ok(u) => u,
            Err(e) => {
                eprintln!("[知几更新] Updater init failed: {}", e);
                return;
            }
        };

        let update = match updater.check().await {
            Ok(Some(u)) => u,
            Ok(None) => {
                eprintln!("[知几更新] 已是最新版本");
                return;
            }
            Err(e) => {
                eprintln!("[知几更新] 检查失败: {}", e);
                return;
            }
        };

        eprintln!("[知几更新] 发现新版本 v{}", update.version);
        let _ = handle.emit("update-available", serde_json::json!({
            "version": update.version,
            "message": format!("发现新版本 v{}，正在下载...", update.version)
        }));

        let handle1 = handle.clone();
        match update
            .download_and_install(
                {
                    let mut downloaded: u64 = 0;
                    move |chunk, total| {
                        downloaded += chunk as u64;
                        let (pct, msg) = if let Some(t) = total {
                            let p = if t > 0 { (downloaded as f64 / t as f64 * 100.0) as u32 } else { 0 };
                            (p, format!("下载中 {}%", p))
                        } else {
                            let mb = downloaded as f64 / 1_048_576.0;
                            (0, format!("下载中 {:.1} MB", mb))
                        };
                        let _ = handle1.emit("update-progress", serde_json::json!({
                            "stage": "downloading",
                            "percent": pct,
                            "message": msg
                        }));
                    }
                },
                || {
                    let _ = handle.emit("update-progress", serde_json::json!({
                        "stage": "installing",
                        "percent": 100,
                        "message": "安装中，即将重启..."
                    }));
                },
            )
            .await
        {
            Ok(()) => {
                let _ = handle.emit("update-progress", serde_json::json!({
                    "stage": "done",
                    "percent": 100,
                    "message": "更新完成，即将重启"
                }));
                handle.restart();
            }
            Err(e) => {
                eprintln!("[知几更新] 安装失败: {}", e);
                let _ = handle.emit("update-progress", serde_json::json!({
                    "stage": "error",
                    "percent": 0,
                    "message": format!("安装失败: {}", e)
                }));
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
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            get_desktop_version,
            check_updates,
            get_crash_logs
        ])
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
                .title("知几")
                .inner_size(500.0, 340.0)
                .resizable(false)
                .decorations(false)
                .always_on_top(true)
                .skip_taskbar(true)
                .center()
                .visible(true)
                .build()?;

            // --- Kill stale backend ---
            let _ = Command::new("lsof")
                .args(["-ti", ":9120"])
                .output()
                .ok()
                .and_then(|o| {
                    if o.status.success() && !o.stdout.is_empty() {
                        let pids = String::from_utf8_lossy(&o.stdout);
                        eprintln!("[知几] 清理旧后端 PID: {}", pids.trim());
                        let _ = Command::new("kill")
                            .args(["-9"])
                            .args(pids.split_whitespace())
                            .output();
                    }
                    Some(())
                });
            std::thread::sleep(Duration::from_millis(500));

            eprintln!("[知几] Python: {:?}  cwd: {:?}", venv_python, app_dir);

            // --- Spawn Python backend ---
            let python_home = app_dir.join("python");
            let ki_home = dirs_next(&app_dir);
            migrate_data_if_needed(&ki_home);

            let child = Command::new(&venv_python)
                .args([
                    "-m", "uvicorn", "backend.main:app",
                    "--host", "0.0.0.0", "--port", "9120",
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
                    std::thread::sleep(Duration::from_secs(8));
                    match child.try_wait() {
                        Ok(Some(status)) => {
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
                            let exit_code = status.code()
                                .map(|c| c.to_string())
                                .unwrap_or_else(|| "signal".into());

                            // Save crash log
                            let combined = format!("stdout:\n{}\nstderr:\n{}", stdout_out, stderr_out);
                            save_crash_log(&ki_home, &combined, &exit_code);

                            eprintln!(
                                "[知几] ❌ 后端异常退出 (exit {})\nstderr: {}",
                                exit_code, stderr_out
                            );
                            let detail = format!(
                                "进程异常退出 (exit {})\n\n崩溃日志已保存到 ~/Documents/KI/crashes/\n\n{}",
                                exit_code,
                                stderr_out.chars().take(400).collect::<String>()
                            );
                            show_splash_error(&splash, "启动失败 — 后端异常退出", &detail);
                            false
                        }
                        Ok(None) => {
                            app.manage(BackendProcess(Mutex::new(Some(child))));
                            eprintln!("[知几] ✅ 后端运行中 http://127.0.0.1:9120");
                            true
                        }
                        Err(e) => {
                            eprintln!("[知几] try_wait error: {}", e);
                            show_splash_error(&splash, "启动失败 — 进程状态异常", &e.to_string());
                            false
                        }
                    }
                }
                Err(e) => {
                    let err_str = e.to_string();
                    eprintln!(
                        "[知几] ❌ 后端启动失败\nPython: {:?}\nError: {}\nExists: {:?}",
                        venv_python, err_str, venv_python.exists()
                    );
                    let mut detail = format!("无法启动 Python 后端\n{}", err_str);
                    if err_str.contains("bad CPU") || err_str.contains("Bad CPU") {
                        detail.push_str("\n\n可能需要 Rosetta 2：\nsoftwareupdate --install-rosetta");
                    }
                    if !venv_python.exists() {
                        detail.push_str(&format!("\n\nPython 二进制不存在:\n{:?}", venv_python));
                    }
                    show_splash_error(&splash, "启动失败 — 无法启动后端", &detail);
                    false
                }
            };

            if backend_ok {
                spawn_update_check(app.handle().clone());

                splash.close()?;
                if let Some(main) = app.get_webview_window("main") {
                    main.show()?;
                    main.set_focus()?;
                }

                // --- Drag-drop: handled in frontend via native HTML5 DnD API ---

                // --- System tray ---
                let icon = app.default_window_icon().cloned().unwrap();
                let about = MenuItemBuilder::with_id("about", "关于知几").build(app)?;
                let toggle = MenuItemBuilder::with_id("toggle", "显示/隐藏").build(app)?;
                let quit = MenuItemBuilder::with_id("quit", "退出").build(app)?;
                let menu = MenuBuilder::new(app)
                    .items(&[&about, &toggle, &quit])
                    .build()?;

                let _tray = TrayIconBuilder::new()
                    .icon(icon)
                    .menu(&menu)
                    .tooltip("知几")
                    .on_menu_event(|app, event| match event.id().as_ref() {
                        "about" => {
                            if let Some(w) = app.get_webview_window("about") {
                                w.show().ok();
                                w.set_focus().ok();
                            } else {
                                let _ = tauri::WebviewWindowBuilder::new(
                                    app,
                                    "about",
                                    tauri::WebviewUrl::App("about.html".into()),
                                )
                                .title("关于知几")
                                .inner_size(380.0, 320.0)
                                .resizable(false)
                                .decorations(true)
                                .center()
                                .build();
                            }
                        }
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
