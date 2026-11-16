//! `tasks` and robot-event application.

use async_trait::async_trait;
use domain::ports::TaskRepository;
use domain::{ApplyOutcome, DomainError, ItemId, Page, Task, TaskFilter, TaskId};
use uuid::Uuid;

use domain::{Actor, TaskParts};
use sqlx::Row as _;
use sqlx::sqlite::SqliteRow;

use crate::events::mark_processed;
use crate::pool::Database;
use crate::sql::{corrupt, db, enum_text, parse_enum, parse_id, parse_opt_ts, parse_ts, ts};

const COLUMNS: &str = "SELECT id, kind, item, from_place, to_place, deadline, state, \
     requested_by_json, assigned_robot, failure, needs_human, created_at, updated_at FROM tasks";

/// The bound values of one task row, in column order.
struct TaskRow {
    id: String,
    kind: String,
    item: Option<String>,
    from: Option<String>,
    to: String,
    deadline: Option<String>,
    state: String,
    requested_by_json: String,
    requested_by_user: Option<String>,
    assigned_robot: Option<String>,
    failure: Option<String>,
    needs_human: Option<String>,
    created_at: String,
    updated_at: String,
}

fn row_of(task: &Task) -> Result<TaskRow, DomainError> {
    let requested_by_user = match task.requested_by() {
        Actor::User(user) => Some(user.as_str().to_owned()),
        _ => None,
    };
    Ok(TaskRow {
        id: task.id().as_str().to_owned(),
        kind: enum_text(&task.kind())?,
        item: task.item().map(|i| i.as_str().to_owned()),
        from: task.from().map(|p| p.as_str().to_owned()),
        to: task.to().as_str().to_owned(),
        deadline: task.deadline().map(ts),
        state: enum_text(&task.state())?,
        requested_by_json: serde_json::to_string(task.requested_by())
            .map_err(|_| corrupt("tasks", "requested_by"))?,
        requested_by_user,
        assigned_robot: task.assigned_robot().map(|r| r.as_str().to_owned()),
        failure: task.failure().map(|f| enum_text(&f)).transpose()?,
        needs_human: task.needs_human().map(str::to_owned),
        created_at: ts(task.created_at()),
        updated_at: ts(task.updated_at()),
    })
}

fn task_of(row: &SqliteRow) -> Result<Task, DomainError> {
    let id: String = row.try_get("id").map_err(db)?;
    let kind: String = row.try_get("kind").map_err(db)?;
    let item: Option<String> = row.try_get("item").map_err(db)?;
    let from: Option<String> = row.try_get("from_place").map_err(db)?;
    let to: String = row.try_get("to_place").map_err(db)?;
    let deadline: Option<String> = row.try_get("deadline").map_err(db)?;
    let state: String = row.try_get("state").map_err(db)?;
    let requested_by: String = row.try_get("requested_by_json").map_err(db)?;
    let robot: Option<String> = row.try_get("assigned_robot").map_err(db)?;
    let failure: Option<String> = row.try_get("failure").map_err(db)?;
    let created: String = row.try_get("created_at").map_err(db)?;
    let updated: String = row.try_get("updated_at").map_err(db)?;
    Task::restore(TaskParts {
        id: parse_id("tasks", &id)?,
        kind: parse_enum("tasks", &kind)?,
        item: item.map(|i| parse_id("tasks", &i)).transpose()?,
        from: from.map(|p| parse_id("tasks", &p)).transpose()?,
        to: parse_id("tasks", &to)?,
        deadline: parse_opt_ts("tasks", deadline)?,
        state: parse_enum("tasks", &state)?,
        requested_by: serde_json::from_str(&requested_by)
            .map_err(|_| corrupt("tasks", "requested_by"))?,
        assigned_robot: robot.map(|r| parse_id("tasks", &r)).transpose()?,
        failure: failure.map(|f| parse_enum("tasks", &f)).transpose()?,
        needs_human: row.try_get("needs_human").map_err(db)?,
        created_at: parse_ts("tasks", &created)?,
        updated_at: parse_ts("tasks", &updated)?,
    })
}

fn not_found(id: &TaskId) -> DomainError {
    DomainError::NotFound {
        what: format!("Task '{id}'"),
    }
}

/// Saves the changed fields of a task; `false` when no row has its id.
async fn update_on(conn: &mut sqlx::SqliteConnection, task: &Task) -> Result<bool, DomainError> {
    let row = row_of(task)?;
    let done = sqlx::query(
        "UPDATE tasks SET kind = ?, item = ?, from_place = ?, to_place = ?, deadline = ?, \
         state = ?, requested_by_json = ?, requested_by_user = ?, assigned_robot = ?, \
         failure = ?, needs_human = ?, created_at = ?, updated_at = ? WHERE id = ?",
    )
    .bind(row.kind)
    .bind(row.item)
    .bind(row.from)
    .bind(row.to)
    .bind(row.deadline)
    .bind(row.state)
    .bind(row.requested_by_json)
    .bind(row.requested_by_user)
    .bind(row.assigned_robot)
    .bind(row.failure)
    .bind(row.needs_human)
    .bind(row.created_at)
    .bind(row.updated_at)
    .bind(row.id)
    .execute(conn)
    .await
    .map_err(db)?;
    Ok(done.rows_affected() == 1)
}

/// Tasks in SQLite.
#[derive(Debug, Clone)]
pub struct SqliteTaskRepository {
    db: Database,
}

impl SqliteTaskRepository {
    /// On a database.
    #[must_use]
    pub fn new(db: Database) -> SqliteTaskRepository {
        SqliteTaskRepository { db }
    }
}

#[async_trait]
impl TaskRepository for SqliteTaskRepository {
    async fn insert(&self, task: &Task) -> Result<(), DomainError> {
        let row = row_of(task)?;
        sqlx::query(
            "INSERT INTO tasks (id, kind, item, from_place, to_place, deadline, state, \
             requested_by_json, requested_by_user, assigned_robot, failure, needs_human, \
             created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(row.id)
        .bind(row.kind)
        .bind(row.item)
        .bind(row.from)
        .bind(row.to)
        .bind(row.deadline)
        .bind(row.state)
        .bind(row.requested_by_json)
        .bind(row.requested_by_user)
        .bind(row.assigned_robot)
        .bind(row.failure)
        .bind(row.needs_human)
        .bind(row.created_at)
        .bind(row.updated_at)
        .execute(self.db.pool())
        .await
        .map_err(|error| match &error {
            sqlx::Error::Database(e) if e.is_unique_violation() => DomainError::Conflict {
                what: format!("Task '{}'", task.id()),
            },
            _ => db(error),
        })?;
        Ok(())
    }
    async fn update(&self, task: &Task) -> Result<(), DomainError> {
        let mut conn = self.db.pool().acquire().await.map_err(db)?;
        if update_on(&mut conn, task).await? {
            Ok(())
        } else {
            Err(not_found(task.id()))
        }
    }
    async fn get(&self, id: &TaskId) -> Result<Option<Task>, DomainError> {
        let row = sqlx::query(sqlx::AssertSqlSafe(format!("{COLUMNS} WHERE id = ?")))
            .bind(id.as_str())
            .fetch_optional(self.db.pool())
            .await
            .map_err(db)?;
        row.as_ref().map(task_of).transpose()
    }
    async fn list(&self, filter: &TaskFilter, page: &Page) -> Result<Vec<Task>, DomainError> {
        let rows = sqlx::query(sqlx::AssertSqlSafe(format!(
            "{COLUMNS} WHERE (?1 IS NULL OR state = ?1) AND (?2 IS NULL OR assigned_robot = ?2) \
             AND (?3 IS NULL OR requested_by_user = ?3) AND (?4 IS NULL OR created_at >= ?4) \
             AND (?5 = 0 OR state NOT IN ('delivered', 'failed', 'cancelled')) \
             ORDER BY created_at DESC, id DESC LIMIT ?6 OFFSET ?7"
        )))
        .bind(filter.state.map(|s| enum_text(&s)).transpose()?)
        .bind(filter.robot.as_ref().map(|r| r.as_str().to_owned()))
        .bind(filter.requested_by.as_ref().map(|u| u.as_str().to_owned()))
        .bind(filter.since.map(ts))
        .bind(i64::from(filter.active_only))
        .bind(i64::from(page.limit()))
        .bind(i64::from(page.offset()))
        .fetch_all(self.db.pool())
        .await
        .map_err(db)?;
        rows.iter().map(task_of).collect()
    }
    async fn apply_robot_event(
        &self,
        event_id: Uuid,
        task: &Task,
        stock_decrement: Option<(&ItemId, u32)>,
    ) -> Result<ApplyOutcome, DomainError> {
        let mut tx = self
            .db
            .pool()
            .begin_with("BEGIN IMMEDIATE")
            .await
            .map_err(db)?;
        if !mark_processed(&mut tx, event_id).await? {
            return Ok(ApplyOutcome::Duplicate);
        }
        if !update_on(&mut tx, task).await? {
            return Err(not_found(task.id()));
        }
        if let Some((item, qty)) = stock_decrement {
            let count: Option<i64> =
                sqlx::query_scalar("SELECT count FROM inventory WHERE item = ?")
                    .bind(item.as_str())
                    .fetch_optional(&mut *tx)
                    .await
                    .map_err(db)?;
            let Some(count) = count else {
                return Err(DomainError::NotFound {
                    what: format!("Item '{item}'"),
                });
            };
            if count < i64::from(qty) {
                return Err(DomainError::InsufficientStock {
                    item: item.clone(),
                    requested: qty,
                    available: u32::try_from(count).unwrap_or(0),
                });
            }
            sqlx::query("UPDATE inventory SET count = count - ?, updated_at = ? WHERE item = ?")
                .bind(i64::from(qty))
                .bind(ts(chrono::Utc::now()))
                .bind(item.as_str())
                .execute(&mut *tx)
                .await
                .map_err(db)?;
        }
        tx.commit().await.map_err(db)?;
        Ok(ApplyOutcome::Applied)
    }
}
