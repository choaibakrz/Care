//! Serves the built admin console (`implementation/admin/dist`) at `/admin/`, so phones and
//! laptops open the console from the server itself (same origin as the API). The folder is
//! `ADMIN_WEB_DIR`, by default `../admin/dist` (relative to the server's working directory).
//! A path that is not a file falls back to `index.html` (single-page app). When the folder
//! has no `index.html`, `/admin/` answers 404 and nothing else changes.

use std::path::PathBuf;
use std::sync::Arc;

use axum::Router;
use axum::extract::{Path as UrlPath, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse as _, Redirect, Response};
use axum::routing::get;

use crate::patient::static_files::read_file;

/// Default folder of the built console.
const DEFAULT_ADMIN_WEB_DIR: &str = "../admin/dist";

type Root = State<Arc<PathBuf>>;

/// `/admin`, `/admin/` and `/admin/{*path}`. The API's `/admin/accounts` and
/// `/admin/enrolment-codes` are more specific routes and keep priority.
pub fn router() -> Router {
    let root = std::env::var_os("ADMIN_WEB_DIR")
        .map_or_else(|| PathBuf::from(DEFAULT_ADMIN_WEB_DIR), PathBuf::from);
    Router::new()
        .route("/admin", get(|| async { Redirect::permanent("/admin/") }))
        .route("/admin/", get(index))
        .route("/admin/{*path}", get(file))
        .with_state(Arc::new(root))
}

async fn index(State(root): Root) -> Response {
    read_file(&root, "index.html")
        .await
        .unwrap_or_else(not_built)
}

async fn file(State(root): Root, UrlPath(path): UrlPath<String>) -> Response {
    if let Some(found) = read_file(&root, &path).await {
        return found;
    }
    // A missing asset (`assets/x.js`) is a 404; a client-side route falls back to the app.
    let is_asset = path
        .rsplit('/')
        .next()
        .is_some_and(|name| name.contains('.'));
    if is_asset {
        return (StatusCode::NOT_FOUND, "not found").into_response();
    }
    index(State(root)).await
}

fn not_built() -> Response {
    (
        StatusCode::NOT_FOUND,
        "The admin console is not built: run `pnpm build` in implementation/admin \
         (or set ADMIN_WEB_DIR).",
    )
        .into_response()
}
