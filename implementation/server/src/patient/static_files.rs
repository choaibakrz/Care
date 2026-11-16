//! Serves the patient web app (`implementation/patient-web`) at `/patient/`, so the app and
//! the API share one origin. The folder is `PATIENT_WEB_DIR`, by default `../patient-web`
//! (relative to the server's working directory).

use std::path::{Component, Path, PathBuf};
use std::sync::Arc;

use axum::Router;
use axum::extract::{Path as UrlPath, State};
use axum::http::{StatusCode, header};
use axum::response::{IntoResponse, Redirect, Response};
use axum::routing::get;

use super::PatientError;

/// Default folder of the patient web app.
const DEFAULT_PATIENT_WEB_DIR: &str = "../patient-web";

type Root = State<Arc<PathBuf>>;

/// `/patient`, `/patient/` and `/patient/{*path}`.
pub(super) fn router() -> Router {
    let root = std::env::var_os("PATIENT_WEB_DIR")
        .map_or_else(|| PathBuf::from(DEFAULT_PATIENT_WEB_DIR), PathBuf::from);
    Router::new()
        .route(
            "/patient",
            get(|| async { Redirect::permanent("/patient/") }),
        )
        .route("/patient/", get(index))
        .route("/patient/{*path}", get(file))
        .with_state(Arc::new(root))
}

async fn index(State(root): Root) -> Response {
    serve(&root, "index.html").await
}

async fn file(State(root): Root, UrlPath(path): UrlPath<String>) -> Response {
    serve(&root, &path).await
}

async fn serve(root: &Path, relative: &str) -> Response {
    read_file(root, relative).await.unwrap_or_else(not_found)
}

/// The file `relative` under `root` (`index.html` for a folder), or `None` when the path is
/// not a plain relative path (no `..`, no root, no drive prefix) or the file cannot be read.
/// Shared with the admin console's static serving (`crate::admin_web`).
pub(crate) async fn read_file(root: &Path, relative: &str) -> Option<Response> {
    let relative = if relative.is_empty() || relative.ends_with('/') {
        format!("{relative}index.html")
    } else {
        relative.to_owned()
    };
    let path = Path::new(&relative);
    // Only plain names: no `..`, no root, no drive prefix.
    if !path
        .components()
        .all(|component| matches!(component, Component::Normal(_)))
    {
        return None;
    }
    let bytes = tokio::fs::read(root.join(path)).await.ok()?;
    Some(
        (
            [
                (header::CONTENT_TYPE, content_type(path)),
                (header::CACHE_CONTROL, "no-cache"),
            ],
            bytes,
        )
            .into_response(),
    )
}

fn not_found() -> Response {
    PatientError::with_status(
        StatusCode::NOT_FOUND,
        "not_found",
        "This page of the patient app does not exist.",
    )
    .into_response()
}

fn content_type(path: &Path) -> &'static str {
    match path.extension().and_then(|ext| ext.to_str()) {
        Some("html") => "text/html; charset=utf-8",
        Some("js" | "mjs") => "text/javascript; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("svg") => "image/svg+xml",
        Some("json" | "map") => "application/json",
        Some("png") => "image/png",
        Some("ico") => "image/x-icon",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("webp") => "image/webp",
        Some("woff2") => "font/woff2",
        Some("woff") => "font/woff",
        Some("wasm") => "application/wasm",
        Some("glb") => "model/gltf-binary",
        Some("gltf") => "model/gltf+json",
        Some("webmanifest") => "application/manifest+json",
        _ => "text/plain; charset=utf-8",
    }
}
