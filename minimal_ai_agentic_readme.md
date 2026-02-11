# minimal.ai --- Agentic AI System Roadmap

## Vision

Transform minimal.ai from a **chat-based AI** into a **true autonomous
agent** that can plan, decide, and execute real-world actions across
apps and services.

------------------------------------------------------------------------

## Core Architecture Shift

### From:

Prompt → LLM → Text Response

### To:

Intent → Planner → Tool Execution → Feedback Loop → Completed Task

This loop is the foundation of **Cursor‑like / Devin‑style agentic
systems**.

------------------------------------------------------------------------

## System Components You Must Build

### 1. Intent Parser

-   Detect user goal from natural language
-   Classify complexity and required capabilities
-   Route to planner

### 2. Planner (Agent Brain)

-   LLM generates **structured execution plan (JSON)**
-   Breaks task into ordered steps
-   Chooses correct tools
-   Supports retries and self‑correction

### 3. Tool Registry (Action Layer)

Create executable tools such as:

-   Send Email
-   Open Apps
-   File System Access
-   Browser Automation
-   Android UI Control
-   API Integrations

Each tool must: - Accept structured arguments - Return structured
result - Be observable and retryable

------------------------------------------------------------------------

## 4. Execution Engine (Agent Loop)

Core loop:

1.  Read next step from plan
2.  Execute tool
3.  Store result in memory
4.  Re‑evaluate task completion
5.  Continue until done

This converts **AI response → real‑world action**.

------------------------------------------------------------------------

## 5. Memory System

### Short‑term

-   Step history
-   Tool outputs
-   Errors

### Long‑term

-   User preferences
-   Past successful strategies
-   Behavioral patterns

Store inside **MongoDB** and embed for retrieval later.

------------------------------------------------------------------------

## 6. Android Autonomy Layer

### Accessibility Service (Primary)

Allows AI to: - Tap buttons - Type text - Scroll - Navigate apps - Send
messages/emails

### Intents (Safer production control)

-   Send email
-   Create reminders
-   Launch apps

### ADB (Prototype only)

-   Useful during development
-   Not for production release

------------------------------------------------------------------------

## 7. Safety & Permissions

Must include:

-   Explicit user confirmations for sensitive actions
-   Scoped permissions per tool
-   Rate limiting
-   Execution logs
-   Emergency stop

Without safety → cannot ship publicly.

------------------------------------------------------------------------

## 8. Observability

Track:

-   Plan chosen
-   Tools executed
-   Latency
-   Cost
-   Failures
-   Retries

Store per‑request analytics for improvement.

------------------------------------------------------------------------

## 9. Development Phases

### Phase 1 --- Core Agent Brain

-   Planner endpoint
-   Tool registry
-   Execution loop
-   Step memory

**Result:** Real agent backend

------------------------------------------------------------------------

### Phase 2 --- Android Control

-   Accessibility automation
-   Intent integrations
-   Permission + safety layer

**Result:** AI that operates the phone

------------------------------------------------------------------------

### Phase 3 --- Intelligence Upgrade

-   Long‑term memory
-   Self‑reflection
-   Multi‑step reasoning
-   Error recovery

**Result:** Cursor/Devin‑level autonomy

------------------------------------------------------------------------

## 10. Final Outcome

minimal.ai becomes:

-   Autonomous task executor
-   Cross‑app AI assistant
-   Real‑world action agent
-   Startup‑grade product

------------------------------------------------------------------------

## Author Note

If you build all layers above, this is **no longer a student project**
--- it becomes a **fundable AI startup system**.
