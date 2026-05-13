# TaskCall-PerceptionMap

`TaskCall-PerceptionMap` is a lightweight Python prototype for
task-structured, DAG-driven agent execution.

It explores how a complex problem can be decomposed into explicit plan nodes,
executed with controlled capabilities, and stitched back together through
structured artifacts, transcripts, and scheduler state.

## Why this project exists

Many agent demos focus on a single loop that calls an LLM until it returns an
answer. This project takes a different angle:

- break a task into explicit subproblems
- model dependencies as a DAG
- run each node through a controlled execution loop
- preserve intermediate artifacts and transcripts
- make capability use and downstream data flow visible

The result is a small but concrete runtime shape that can later be connected to
real planners, model providers, and retrieval systems.

## What is implemented

- Plan and execution domain models
- Planner-facing contracts for online planning and case retrieval
- A DAG scheduler that runs ready nodes and unlocks downstream work
- A loop engine for per-node execution
- Capability registration and permission gating
- Structured artifact passing between nodes
- In-memory stores for artifacts, sessions, transcripts, and worker agents
- Nested worker-agent execution through adapter-backed runtimes

## Repository layout

```text
TaskCall-PerceptionMap/
  taskcall_perception_map/
    agents/
    capabilities/
    domain/
    llm/
    planner/
    runtime/
    scheduler/
    storage/
  examples/
    minimal_demo.py
    llm_factory_demo.py
  pyproject.toml
  README.md
```

## Current scope

This repository is intentionally focused on runtime structure, not product
surface area.

Included:

- execution orchestration
- node-local loop control
- capability invocation
- transcript recording
- nested worker-agent flow

Not included yet:

- CLI
- Web UI
- persistent database
- production LLM integrations
- plugin ecosystem

## Quick start

Use Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Run the minimal demo:

```bash
python -m examples.minimal_demo
```

The demo builds a small three-node plan, executes dependency-aware node runs,
spawns a child worker for a delegated aggregation step, and prints resulting
artifacts, node states, and transcript counts.

## Core ideas

### 1. Explicit plan graph

Tasks are represented as nodes with:

- a goal
- declared dependencies
- expected outputs
- allowed capabilities
- an agent profile

This keeps decomposition visible instead of hiding it inside a single prompt.

### 2. Structured execution loop

Each node is executed through a loop engine that can process steps such as:

- continue thinking
- call a capability
- spawn a child agent
- complete with artifacts
- fail with a reason

This keeps node execution inspectable and easier to validate.

### 3. Artifact-first data flow

Upstream nodes do not merely return free-form text. They emit typed artifacts
that downstream nodes can consume through explicit selectors.

### 4. Planner/runtime separation

Planner-side protocols are defined separately from runtime mechanics so future
planners, retrievers, or case-based decomposition systems can plug in without
rewriting the scheduler.

## Example use case

The included demo solves a small arithmetic word problem by:

1. computing one contributor's amount
2. computing another contributor's amount
3. aggregating the total after dependency resolution
4. delegating a final sum step to a child worker agent

Even though the example is simple, it exercises the main runtime shape:
planning outputs, DAG scheduling, capability use, child-agent execution, and
artifact propagation.

## Roadmap ideas

- add a real planner implementation
- add retrieval-backed case reuse
- plug in production LLM providers
- persist transcripts and artifacts beyond memory
- expose execution traces through a UI or CLI

## License

No license has been added yet. If you plan to make this repository broadly
reusable, adding a license is a good next step.
