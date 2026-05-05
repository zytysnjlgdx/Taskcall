# TaskCall-PerceptionMap

This directory contains a standalone Python skeleton for a task-structured,
DAG-driven execution runtime.

It borrows the core architectural ideas from the surrounding Claude Code-style
project without copying the full shell:

- a session-level orchestrator
- a loop-based node execution engine
- explicit capability registration and gating
- structured artifact passing between nodes
- persistent transcripts and session snapshots

## Layout

```text
TaskCall—PerceptionMap/
  taskcall_perception_map/
    domain/
    planner/
    scheduler/
    runtime/
    capabilities/
    storage/
  examples/
    minimal_demo.py
```

## What is implemented

- Domain models for plans, nodes, artifacts, task packages, transcripts, and
  scheduler summaries
- In-memory stores for artifacts, sessions, and transcripts
- A capability registry plus a simple permission gate
- A loop engine that can:
  - ask an adapter for the next step
  - invoke a capability when requested
  - validate final node outputs
- A node runner that builds task packages and hands them to the loop engine
- An execution scheduler that walks a DAG, runs ready nodes, writes artifacts,
  and unlocks downstream nodes

## What is intentionally left light

- No CLI
- No web UI
- No database
- No real LLM provider integration
- No plugin system

The point of this first pass is to make the runtime shape concrete before you
wire in a real planner or model backend.

## Run the demo

From this directory:

```bash
python -m examples.minimal_demo
```

The demo runs a tiny three-node plan and prints the resulting artifacts and
node states.
