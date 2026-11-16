//! `POST /tasks`, `GET /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel`,
//! `GET /tasks/{id}/route`.

use axum::Json;
use axum::extract::State;
use axum::http::StatusCode;
use domain::{ErrorBody, TaskId};

use crate::dto::{NewTask, RouteView, TaskListQuery, TaskPage, TaskView};
use crate::error::{ApiError, ApiJson, ApiPath, ApiQuery};
use crate::extractors::{Authorized, perm};
use crate::state::AppState;

/// Creates a task (fetch, restock round, go to). The dispatcher then picks a robot or hands
/// the task to a human with an explanation.
#[utoipa::path(
    post,
    path = "/tasks",
    tag = "tasks",
    request_body = NewTask,
    responses(
        (status = 201, description = "Task created", body = TaskView),
        (status = 403, description = "Role may not create tasks", body = ErrorBody),
        (status = 409, description = "Item out of stock", body = ErrorBody),
        (status = 422, description = "Unknown place or item, or invalid request", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn create(
    State(state): State<AppState>,
    auth: Authorized<perm::CreateTask>,
    ApiJson(new): ApiJson<NewTask>,
) -> Result<(StatusCode, Json<TaskView>), ApiError> {
    let task = state.tasks.create(&auth.identity, new).await?;
    Ok((StatusCode::CREATED, Json(task)))
}

/// Lists tasks, newest first, with optional filters and pagination: `{items, next}`.
#[utoipa::path(
    get,
    path = "/tasks",
    tag = "tasks",
    params(TaskListQuery),
    responses(
        (status = 200, description = "A page of tasks", body = TaskPage),
        (status = 422, description = "Invalid filter or page", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn list(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewTasks>,
    ApiQuery(query): ApiQuery<TaskListQuery>,
) -> Result<Json<TaskPage>, ApiError> {
    let (filter, page) = query.into_parts()?;
    Ok(Json(state.tasks.list(filter, page).await?))
}

/// One task by id.
#[utoipa::path(
    get,
    path = "/tasks/{id}",
    tag = "tasks",
    params(("id" = String, Path, description = "Task id")),
    responses(
        (status = 200, description = "The task", body = TaskView),
        (status = 404, description = "No such task", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn get(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewTasks>,
    ApiPath(id): ApiPath<TaskId>,
) -> Result<Json<TaskView>, ApiError> {
    Ok(Json(state.tasks.get(&id).await?))
}

/// Cancels a task (admin, or the user who requested it). Allowed only while it is
/// `requested` or `assigned`; the task ends in state `cancelled`.
#[utoipa::path(
    post,
    path = "/tasks/{id}/cancel",
    tag = "tasks",
    params(("id" = String, Path, description = "Task id")),
    responses(
        (status = 200, description = "Task cancelled", body = TaskView),
        (status = 403, description = "Neither admin nor the requester", body = ErrorBody),
        (status = 404, description = "No such task", body = ErrorBody),
        (status = 409, description = "Task already en route or finished", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn cancel(
    State(state): State<AppState>,
    auth: Authorized<perm::CancelTask>,
    ApiPath(id): ApiPath<TaskId>,
) -> Result<Json<TaskView>, ApiError> {
    Ok(Json(state.tasks.cancel(&auth.identity, &id).await?))
}

/// The estimated remaining path of a task on the active plan (Task 13b): around walls,
/// solid furniture and restricted zones, through deaf zones. **An estimate**: the real robot
/// plans its own way.
#[utoipa::path(
    get,
    path = "/tasks/{id}/route",
    tag = "tasks",
    params(("id" = String, Path, description = "Task id")),
    responses(
        (status = 200, description = "The estimated path", body = RouteView),
        (status = 404, description = "No such task (code `not_found`), or no route can be drawn (code `no_route`, the reason in the message)", body = ErrorBody)
    ),
    security(("bearer" = []))
)]
pub async fn route(
    State(state): State<AppState>,
    _auth: Authorized<perm::ViewTasks>,
    ApiPath(id): ApiPath<TaskId>,
) -> Result<Json<RouteView>, ApiError> {
    Ok(Json(state.routes.task_route(&id).await?))
}
