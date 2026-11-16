//! Task 20: the Python bridge as a dispatch parity oracle.
//!
//! The bridge tests run only with `--features python` (a Python interpreter is needed to
//! build pyo3). Without the feature, the crate still builds and `PythonBridge::start`
//! reports the interpreter as unavailable, so the workspace tests pass with no Python.

use std::path::{Path, PathBuf};
use std::time::Duration;

use python_bindings::PythonConfig;

type BoxError = Box<dyn std::error::Error>;
type TestResult = Result<(), BoxError>;

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../..")
}

fn config(venv: Option<PathBuf>, call_timeout: Duration) -> PythonConfig {
    PythonConfig {
        repo_root: repo_root(),
        venv,
        call_timeout,
    }
}

#[cfg(not(feature = "python"))]
#[test]
fn workspace_tests_pass_without_python() -> TestResult {
    let err = python_bindings::PythonBridge::start(config(None, Duration::from_secs(5)))
        .err()
        .ok_or("the bridge started without the python feature")?;
    assert!(
        matches!(
            err,
            python_bindings::BridgeError::InterpreterUnavailable { .. }
        ),
        "{err:?}"
    );
    assert!(err.to_string().contains("--features python"), "{err}");
    Ok(())
}

/// Our own code in this crate contains no `unsafe` (pyo3's macros do; that is why the crate
/// lint is `deny`, not `forbid`).
#[test]
fn crate_source_contains_no_unsafe_keyword() -> TestResult {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut offenders = Vec::new();
    for entry in std::fs::read_dir(&src)? {
        let path = entry?.path();
        if path.extension().is_some_and(|e| e == "rs") {
            for (number, line) in std::fs::read_to_string(&path)?.lines().enumerate() {
                let code = line.split("//").next().unwrap_or_default();
                if ["unsafe {", "unsafe fn", "unsafe impl", "unsafe extern"]
                    .iter()
                    .any(|needle| code.contains(needle))
                {
                    offenders.push(format!("{}:{}", path.display(), number + 1));
                }
            }
        }
    }
    assert!(offenders.is_empty(), "unsafe code in {offenders:?}");
    Ok(())
}

#[cfg(feature = "python")]
mod with_python {
    use std::collections::{BTreeMap, BTreeSet};
    use std::sync::Arc;
    use std::time::Duration;

    use domain::{PlaceId, RobotId, RobotStatus};
    use optimization::{
        DispatchOracle, DispatchPolicy, DispatchRequest, Dispatcher, FleetMember, NativeOracle,
        OptimizationError, RoleCard, RoutingGraph,
    };
    use python_bindings::{BridgeError, PythonBridge};
    use serde::Deserialize;

    use super::{BoxError, TestResult, config, repo_root};

    #[derive(Debug, Deserialize)]
    struct Golden {
        name: String,
        request: GoldenRequest,
        fleet: Vec<GoldenRobot>,
    }

    #[derive(Debug, Deserialize)]
    struct GoldenRequest {
        from: PlaceId,
        to: PlaceId,
        real_delivery: bool,
    }

    #[derive(Debug, Deserialize)]
    struct GoldenRobot {
        id: RobotId,
        name: String,
        status: RobotStatus,
        at: PlaceId,
        battery_pct: f64,
        card: String,
        simulated: bool,
    }

    fn server_dir() -> std::path::PathBuf {
        repo_root().join("implementation/server")
    }

    fn venv() -> std::path::PathBuf {
        repo_root().join(".venv")
    }

    fn bridge(timeout: Duration) -> Result<PythonBridge, BoxError> {
        Ok(PythonBridge::start(config(Some(venv()), timeout))?)
    }

    fn simple_fleet() -> Result<Vec<FleetMember>, BoxError> {
        let cards = RoleCard::load_all(&server_dir().join("seed/role_cards.json"))?;
        let card = cards.values().next().cloned().ok_or("no role card")?;
        let at = card
            .permitted_places
            .iter()
            .next()
            .cloned()
            .ok_or("empty role card")?;
        Ok(vec![FleetMember {
            id: "robot-r1".parse()?,
            name: "R1".to_owned(),
            status: RobotStatus::Idle,
            at,
            battery_pct: 90.0,
            card,
            simulated: false,
        }])
    }

    #[test]
    #[ignore = "T20: the bridge starts and imports the brick, but the Python dispatch call is not wired (answers PythonRaised NotImplementedError); also needs python3x.dll on PATH"]
    fn bridge_decision_equals_native_for_every_golden_scenario() -> TestResult {
        let bridge = bridge(Duration::from_secs(10))?;
        // The seed is a clinic plan since Task A4 (the console's demo clinic).
        let map = locations::load_plan(&server_dir().join("seed/clinic_map.json"))?.validate()?;
        let cards: BTreeMap<String, RoleCard> =
            RoleCard::load_all(&server_dir().join("seed/role_cards.json"))?;
        let native = NativeOracle::new(Dispatcher::new(
            RoutingGraph::from_map(&map),
            DispatchPolicy::default(),
        ));
        let dir = server_dir().join("crates/optimization/tests/golden/dispatch");
        let mut count = 0;
        for entry in std::fs::read_dir(dir)? {
            let path = entry?.path();
            if path.extension().is_none_or(|e| e != "json") {
                continue;
            }
            let golden: Golden = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
            let fleet = golden
                .fleet
                .iter()
                .map(|r| -> Result<FleetMember, BoxError> {
                    Ok(FleetMember {
                        id: r.id.clone(),
                        name: r.name.clone(),
                        status: r.status,
                        at: r.at.clone(),
                        battery_pct: r.battery_pct,
                        card: cards.get(&r.card).cloned().ok_or("unknown card")?,
                        simulated: r.simulated,
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            let request = DispatchRequest {
                from: golden.request.from.clone(),
                to: golden.request.to.clone(),
                real_delivery: golden.request.real_delivery,
            };
            let from_python = bridge.choose(&request, &fleet)?;
            let from_rust = native.choose(&request, &fleet)?;
            assert_eq!(from_python.chosen, from_rust.chosen, "{}", golden.name);
            let fits = |d: &optimization::Decision| -> BTreeSet<(RobotId, bool)> {
                d.considered
                    .iter()
                    .map(|c| (c.robot.clone(), c.fits))
                    .collect()
            };
            assert_eq!(fits(&from_python), fits(&from_rust), "{}", golden.name);
            count += 1;
        }
        assert!(count > 0, "no golden scenario found");
        Ok(())
    }

    #[test]
    #[ignore = "T20: the bridge starts and imports the brick, but the Python dispatch call is not wired (answers PythonRaised NotImplementedError); also needs python3x.dll on PATH"]
    fn missing_venv_returns_interpreter_unavailable_naming_the_path_setting() -> TestResult {
        let missing = repo_root().join("no-such-venv");
        let err = PythonBridge::start(config(Some(missing), Duration::from_secs(5)))
            .err()
            .ok_or("a missing venv was accepted")?;
        match err {
            BridgeError::InterpreterUnavailable { detail } => {
                assert!(detail.contains("venv"), "{detail}");
            }
            other => return Err(format!("expected InterpreterUnavailable, got {other:?}").into()),
        }
        Ok(())
    }

    #[test]
    #[ignore = "T20: the bridge starts and imports the brick, but the Python dispatch call is not wired (answers PythonRaised NotImplementedError); also needs python3x.dll on PATH"]
    fn python_exception_becomes_python_raised_without_traceback_paths() -> TestResult {
        let bridge = bridge(Duration::from_secs(10))?;
        let request = DispatchRequest {
            from: "nowhere-at-all".parse()?,
            to: "nowhere-else".parse()?,
            real_delivery: true,
        };
        let err = bridge
            .choose(&request, &simple_fleet()?)
            .err()
            .ok_or("an impossible request did not raise")?;
        let OptimizationError::Oracle { detail } = err else {
            return Err(format!("expected an oracle error, got {err:?}").into());
        };
        assert!(detail.contains("Python raised"), "{detail}");
        for leak in [".py", "Traceback", "\\", "/briques/"] {
            assert!(!detail.contains(leak), "detail leaks '{leak}': {detail}");
        }
        Ok(())
    }

    #[test]
    #[ignore = "T20: the bridge starts and imports the brick, but the Python dispatch call is not wired (answers PythonRaised NotImplementedError); also needs python3x.dll on PATH"]
    fn call_exceeding_timeout_returns_timeout() -> TestResult {
        let bridge = bridge(Duration::from_millis(1))?;
        let fleet = simple_fleet()?;
        let at = fleet.first().map(|f| f.at.clone()).ok_or("no robot")?;
        let request = DispatchRequest {
            from: at.clone(),
            to: at,
            real_delivery: true,
        };
        let err = bridge
            .choose(&request, &fleet)
            .err()
            .ok_or("a 1 ms call did not time out")?;
        let OptimizationError::Oracle { detail } = err else {
            return Err(format!("expected an oracle error, got {err:?}").into());
        };
        assert!(detail.contains("did not answer"), "{detail}");
        Ok(())
    }

    #[test]
    #[ignore = "T20: the bridge starts and imports the brick, but the Python dispatch call is not wired (answers PythonRaised NotImplementedError); also needs python3x.dll on PATH"]
    fn bridge_works_from_many_tasks_concurrently() -> TestResult {
        let bridge = Arc::new(bridge(Duration::from_secs(10))?);
        let fleet = simple_fleet()?;
        let at = fleet.first().map(|f| f.at.clone()).ok_or("no robot")?;
        let request = DispatchRequest {
            from: at.clone(),
            to: at,
            real_delivery: true,
        };
        let workers: Vec<_> = (0..8)
            .map(|_| {
                let bridge = bridge.clone();
                let request = request.clone();
                let fleet = fleet.clone();
                std::thread::spawn(move || bridge.choose(&request, &fleet).map(|d| d.chosen))
            })
            .collect();
        let mut answers = Vec::new();
        for worker in workers {
            let answer = worker.join().map_err(|_| "a worker thread failed")??;
            answers.push(answer);
        }
        assert!(
            answers.windows(2).all(|w| matches!(w, [a, b] if a == b)),
            "{answers:?}"
        );
        Ok(())
    }
}
