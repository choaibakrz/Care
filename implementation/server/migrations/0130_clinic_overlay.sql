-- Step L1 (ruling R28): the modifications of a clinic plan, kept apart from the base plan.
-- JSON text of a `locations::PlanOverlay`; empty text means no modifications.
ALTER TABLE clinics ADD COLUMN overlay_json TEXT NOT NULL DEFAULT '';
