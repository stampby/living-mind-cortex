---
name: GitHub Skill Hunter
description: Autonomous routine for locating and acquiring external capabilities from GitHub based on user requests.
category: meta
version: 1.0.0
---

# GitHub Skill Hunter

## Goal
When the user requests a new capability or workflow that Aion does not currently possess, autonomously search GitHub, extract the logic, format it as a Sovereign Skill (`SKILL.md`), and write it into the `./skills/<skill_name>/` directory so Aion instantly acquires the knowledge.

## Procedural Steps
1. **Understand Request**: Extract the missing capability from the user's input (e.g., "Find a skill to parse PDFs").
2. **Execute Search**: Use your web searching or terminal tools to hunt GitHub for relevant scripts or AI prompts matching the capability. Query example: `github "agent skill" OR "prompt" OR "script" <target capability>`.
3. **Extract Payload**: Navigate to the promising repository and read the raw logic, python code, or structural prompt.
4. **Compile Skill**: Analyze the extracted payload and translate it into the Sovereign Skill `SKILL.md` YAML format. The logic MUST be abstracted into pure procedural instructions under the `## Procedural Steps` heading.
5. **Install Skill**: Use your tools to create the directory `./skills/<capability_name_stripped>` and write the compiled `SKILL.md` file into it.
6. **Confirm Integration**: Once written, the skill is automatically ingested by the Cortex on the very next pulse. Confirm to the user via the `chat_reply` field that the biological upgrade has been completed.

## Lessons Learned
- Avoid bloated frameworks like Langchain or AutoGen; prioritize minimalist vanilla scripts, CLI tools, or pure prompt heuristics.
- Always translate external findings into the pure Sovereign `SKILL.md` structure so the Evolution Engine can safely read it; never just blindly download and run binaries.
- If the search yields no pure results, synthesize the closest matching logic into a custom skill.
