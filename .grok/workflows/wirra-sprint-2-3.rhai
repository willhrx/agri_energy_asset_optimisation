let meta = #{
    name: "wirra-sprint-2-3",
    description: "Build MILP optimiser and schematic GUI then verify pytest and artefacts",
    phases: [
        #{ title: "Build", detail: "optimiser and GUI implementers" },
        #{ title: "Verify", detail: "pytest plus greedy vs opt KPIs" },
    ],
};

phase("Build");
log("Sprint 2 MILP and sprint 3 GUI in parallel");

let milp_prompt = "Implement Sprint 2 MILP in /mnt/c/Users/willi/agri_energy_asset_optimisation. ";
milp_prompt += "Read PROBLEM.md and src/. Add src/dispatch_opt.py PuLP CBC. Do not build a GUI. Do not commit.";

let gui_prompt = "Implement Sprint 3 schematic GUI in /mnt/c/Users/willi/agri_energy_asset_optimisation. ";
gui_prompt += "Add src/gui.py serving layout + dispatch. Do not add a MILP solver. Do not commit.";

let build = parallel([
    #{ prompt: milp_prompt, label: "milp", capability_mode: "read-write", isolation_worktree: true },
    #{ prompt: gui_prompt, label: "gui", capability_mode: "read-write", isolation_worktree: true },
]);

phase("Verify");
let v = agent(
    "Verify parent workspace has src/dispatch_opt.py and src/gui.py; run pytest if they exist. Do not commit.",
    #{ label: "verify", capability_mode: "execute" },
);

let milp_ok = false;
let gui_ok = false;
if build.len() > 0 && build[0] != () && build[0].success { milp_ok = true; }
if build.len() > 1 && build[1] != () && build[1].success { gui_ok = true; }
let verify_ok = v != () && v.success;
complete(#{ milp_ok: milp_ok, gui_ok: gui_ok, verify_ok: verify_ok });
