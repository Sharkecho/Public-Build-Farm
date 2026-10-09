import fs from "node:fs";
import assert from "node:assert/strict";

const workflowPath = new URL(
  "../.github/workflows/codingos-agent-canvas.yml",
  import.meta.url,
);
const workflow = fs.readFileSync(workflowPath, "utf8");
const dispatchInputs = workflow.match(
  /workflow_dispatch:\s*\n(.*?)(?=\n\s*permissions:)/s,
)?.[1] ?? "";

function check(name, condition) {
  assert.ok(condition, name);
  console.log(`PASS ${name}`);
}

check("manual-only trigger", /^\s+workflow_dispatch:\s*$/m.test(workflow));
check("fixed approved repository", /repository:\s+Sharkecho\/CodingOS-AgentCanvas/.test(workflow));
check("full SHA input", /source_sha:[\s\S]*required:\s+true/.test(workflow));
check("full SHA validation", /\[\[ \"\$SOURCE_SHA\" =~ \^\[0-9a-fA-F\]\{40\}\$/.test(workflow));
check("checkout SHA recorded", /git rev-parse HEAD/.test(workflow));
check("checkout SHA compared", /Checkout SHA mismatch/.test(workflow));
check("read-only permissions", /permissions:\s*\n\s+contents:\s+read/.test(workflow));
check("credential persistence disabled", /persist-credentials:\s+false/.test(workflow));
check("hosted runner pinned", /runs-on:\s+ubuntu-22\.04/.test(workflow));
check("timeout present", /timeout-minutes:\s+30/.test(workflow));
check("source ref is the only source selector", !/inputs:\s*\n(?:.|\n)*source_repo/.test(workflow));
check(
  "no arbitrary command input",
  !/^\s+(command|shell|script):/m.test(dispatchInputs),
);
check("targeted vitest", /npm test -- --run --passWithNoTests __tests__\/codingos/.test(workflow));
check("failure metadata is always attempted", /if: always\(\)/.test(workflow));
check("no push or pull request trigger", !/^\s+(push|pull_request):/m.test(workflow));
check("no source upload", !/path:\s+\.\/?\s*$|path:\s+\$\{\{\s*github\.workspace/.test(workflow));
check("metadata upload is explicit", /build-farm-reports\/codingos\/build-metadata\.json/.test(workflow));
check("metadata contains no secret interpolation", !/secrets\.[A-Z0-9_]+[^\n]*metadata|metadata[^\n]*secrets\./i.test(workflow));

console.log("CodingOS workflow policy validation passed");
