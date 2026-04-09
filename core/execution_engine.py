import asyncio
import time
import re
import random
import html as _html_lib
import os

# ── Safety: paths the runtime must never write to ──────────────────────────
RESTRICTED_DIRS = ["/bin", "/boot", "/etc", "/lib", "/lib64", "/proc", "/sbin", "/sys", "/usr", 
                   "/dev", "/root/.ssh", os.path.expanduser("~/.ssh")]


def _extract_readable(html: str, url: str = "") -> str:
    """
    Extract human-readable text from raw HTML.
    Priority: site-specific selectors → <main> → <article> → <body>
    Strips scripts, styles, nav, header, footer, aside.
    Decodes HTML entities. Filters short nav fragments.
    """
    import re, html as _h

    # Get page title
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _h.unescape(title_m.group(1).strip()) if title_m else url

    # Remove noise tags wholesale
    for tag in ["script", "style", "nav", "header", "footer", "aside",
                "noscript", "svg", "iframe", "form", "dialog", "banner"]:
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", html,
                      flags=re.DOTALL | re.IGNORECASE)

    # Site-specific + generic content selectors (priority order)
    SELECTORS = [
        # GitHub Trending specific
        r'(<article[^>]*?class="Box-row".*?</article>)',
        # GitHub General
        r'<div[^>]+id=["\']readme["\'][^>]*>(.*?)</div\s*>',
        r'<article[^>]+class=[^>]*markdown-body[^>]*>(.*?)</article>',
        r'<div[^>]+class=[^>]*repository-content[^>]*>(.*?)</div\s*>',
        # Generic semantic
        r"<main[^>]*>(.*?)</main>",
        r"<article[^>]*>(.*?)</article>",
        r'<div[^>]+role=["\']main["\'][^>]*>(.*?)</div>',
        r'<div[^>]+id=["\']content["\'][^>]*>(.*?)</div>',
        r'<div[^>]+id=["\']main["\'][^>]*>(.*?)</div>',
        r"<body[^>]*>(.*?)</body>",
    ]

    content = ""
    for pattern in SELECTORS:
        # Use findall for Box-row to get all items
        if "Box-row" in pattern:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            if matches:
                content = "\n---\n".join(matches)
                break
        else:
            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m and len(m.group(1)) > 200:  # must have substance
                content = m.group(1)
                break

    if not content:
        content = html

    # Preserve Links: turn <a ...>text</a> into [LINK: text]
    content = re.sub(r'<a[^>]*>(.*?)</a>', r'[LINK: \1]', content, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining tags
    clean = re.sub(r"<[^>]+>", " ", content)
    # Decode HTML entities
    clean = _h.unescape(clean)
    # Split into lines and filter aggressively
    lines = [l.strip() for l in clean.splitlines()]
    # Drop short lines (nav labels, lone words) and known noise phrases
    NOISE = {"sign in", "sign up", "go to file", "open more", "branches",
             "tags", "code", "folders", "last commit", "you must be signed"}
    lines = [
        l for l in lines
        if len(l) > 40 and not any(n in l.lower() for n in NOISE)
    ]
    clean = "\n".join(lines)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()[:4000]

    return f"[{title}]\n{url}\n\n{clean}" if clean else f"[{title}]\n{url}\n\n(No readable content extracted — page may require login or is JS-only)"


class ExecutionEngine:
    def __init__(self):
        self.pending_actions = []
        self.total_actions = 0
        self.browser = None
        self.page = None

    def stats(self) -> dict:
        return {
            "pending_queue": len(self.pending_actions),
            "total_actions": self.total_actions
        }

    async def propose_action(self, tool: str, args: dict, thought: str):
        self.total_actions += 1
        from api.events import manager
        
        cmd_display = args.get("cmd", args.get("path", args.get("query",
                     args.get("pattern", args.get("url", str(args))))))
        msg = f"→ Motor Cortex executing autonomous tool `{tool}`: {cmd_display}"
        print(f"[EXECUTION] {msg}")
        
        # The UI specifically expects {"type": "function_fire", "tool": tool, "args": cmd_display}
        # We bypass the generic broadcast_event wrapper that forces {"type": "event", "event": "function_fire"}
        payload = {"type": "function_fire", "tool": tool, "args": cmd_display}
        import json
        for conn in manager.active_connections:
            try:
                await conn.send_text(json.dumps(payload))
            except:
                pass
        
        # In a fully sovereign test, we don't wait for human WS approval.
        # We spawn the tool async immediately since we trust the Sandbox.
        from cortex.engine import cortex
        import asyncio
        asyncio.create_task(self._run_tool(tool, args, cortex, manager))

    async def execute_approved(self, cortex, manager):
        if not self.pending_actions:
            return "No pending actions."
        action = self.pending_actions.pop(0)
        self.total_actions += 1
        tool = action["tool"]
        cmd_display = action["args"].get("cmd", action["args"].get(
            "path", action["args"].get("query", action["args"].get(
            "pattern", action["args"].get("url", "")))))
        asyncio.create_task(self._run_tool(tool, action["args"], cortex, manager))
        return f"✓ Running `{tool}`: {cmd_display}"

    async def reject(self):
        if not self.pending_actions:
            return "No pending actions."
        self.pending_actions.clear()
        return "Rejected. Queue cleared."

    # ── Tool Dispatcher ─────────────────────────────────────────────────────
    async def _run_tool(self, tool: str, args: dict, cortex, manager):
        output = ""
        display_output = ""
        try:
            if tool in ("execute_bash", "shell_exec"):
                output, display_output = await self._tool_bash(args)

            elif tool == "read_file":
                output, display_output = await self._tool_read_file(args)

            elif tool == "write_file":
                output, display_output = await self._tool_write_file(args)

            elif tool == "patch_file":
                output, display_output = await self._tool_patch_file(args)

            elif tool == "grep_files":
                output, display_output = await self._tool_grep(args)

            elif tool == "web_search":
                output, display_output = await self._tool_web_search(args)

            elif tool == "fetch_url":
                output, display_output = await self._tool_fetch_url(args)

            elif tool == "browse_web":
                output, display_output = await self._tool_browse_web(args)

            elif tool == "analyze_image":
                output, display_output = await self._tool_analyze_image(args)

            else:
                output = display_output = f"Unknown tool: '{tool}'"

        except Exception as e:
            output = display_output = f"Tool exception: {e}"

        # Store in Cortex memory
        await cortex.remember(
            content=f"[MOTOR SENSORY] Tool '{tool}' returned:\n{output}",
            type="episodic",
            tags=["motor", "feedback", tool],
            importance=0.8,
            emotion="surprise" if "error" in output.lower() or "exception" in output.lower() else "neutral",
            source="experienced"
        )

        # Render output in chat
        import json
        async def _send_chat_reply(content):
            payload = json.dumps({"type": "chat_reply", "content": content})
            for conn in manager.active_connections:
                try:
                    await conn.send_text(payload)
                except Exception:
                    pass

        if display_output:
            lines = display_output.splitlines()[:50]
            truncated = "\n".join(lines)
            if len(display_output.splitlines()) > 50:
                truncated += "\n… (truncated)"
            await _send_chat_reply(f"```shell\n{truncated}\n```")
        else:
            await _send_chat_reply("✓ Done. No output.")
            
        return output, display_output

    # ── Individual Tools ────────────────────────────────────────────────────

    async def _tool_bash(self, args: dict):
        cmd = args.get("cmd", "")
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode().strip()
        err = stderr.decode().strip()
        raw = f"{out}\n{err}".strip()
        display = out if out else err
        return raw, display

    async def _tool_read_file(self, args: dict):
        path = args.get("path", "")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(4000)
        return content, content

    async def _tool_write_file(self, args: dict):
        path = args.get("path", "")
        content = args.get("content", "")
        # Safety check
        for bl in WRITE_BLACKLIST:
            if path.startswith(bl):
                msg = f"BLOCKED: write to {path} is in the safety blacklist."
                return msg, msg
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        msg = f"✓ Written {len(content)} bytes to {path}"
        return msg, msg

    async def _tool_patch_file(self, args: dict):
        path = args.get("path", "")
        old  = args.get("old", "")
        new  = args.get("new", "")
        for bl in WRITE_BLACKLIST:
            if path.startswith(bl):
                msg = f"BLOCKED: patch to {path} is in the safety blacklist."
                return msg, msg
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if old not in content:
            msg = f"Patch failed: target string not found in {path}"
            return msg, msg
        patched = content.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)
        msg = f"✓ Patched {path} ({len(old)} chars → {len(new)} chars)"
        return msg, msg

    async def _tool_grep(self, args: dict):
        pattern  = args.get("pattern", "")
        directory = args.get("directory", os.getcwd())
        glob     = args.get("glob", "*.py")
        proc = await asyncio.create_subprocess_exec(
            "rg", "--color=never", "-n", "--glob", glob, pattern, directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode().strip()
        err = stderr.decode().strip()
        display = out if out else (err or "No matches found.")
        return display, display

    async def _tool_web_search(self, args: dict):
        query = args.get("query", "")
        limit = int(args.get("limit", 5))
        import urllib.request, urllib.parse, re
        url = "https://lite.duckduckgo.com/lite/"
        data = urllib.parse.urlencode({'q': query}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")
        except Exception as e:
            return f"Search failed: {e}", f"Search failed: {e}"

        results = []
        # Find links and clean out HTML tags in titles
        for match in re.finditer(r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE):
            link = str(match.group(1))
            if link.startswith('//'): continue
            title = re.sub(r'<[^>]+>', '', str(match.group(2))).strip()
            results.append(f"• {title} => {link}")
            if len(results) >= limit: break

        if not results:
            display = f"No instant answer or results found for: {query}"
        else:
            display = f"Web search '{query}':\n" + "\n".join(results)
        return display, display

    async def _tool_fetch_url(self, args: dict):
        import urllib.request
        url = args.get("url", "")
        req = urllib.request.Request(url, headers={"User-Agent": "LivingMind/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(50000).decode("utf-8", errors="replace")
        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", " ", raw)
        clean = re.sub(r"\s+", " ", clean).strip()[:3000]
        return clean, clean

    async def _tool_browse_web(self, args: dict):
        import nodriver as uc, os, time
        url = args.get("url", "")
        if url and "://" not in url:
            url = f"https://{url}"
        
        action = args.get("action", "read") # goto | read | screenshot | click_text | type_text | press_key | scroll | close
        target_text = args.get("target_text", "")
        input_text = args.get("input_text", "")
        keys = args.get("keys", "Enter")
        # Add jitter to wait times
        base_wait = float(args.get("wait", 2.0))
        wait = base_wait + random.random() * 2.0

        if action == "close":
            if self.browser:
                try: self.browser.stop()
                except: pass
                self.browser = None
                self.page = None
            return "Browser closed.", "Browser closed."

        if not self.browser:
            # Stealth UA and window jitter
            UAS = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ]
            self.browser = await uc.start(
                headless=False,
                browser_args=[
                    "--no-sandbox", "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    f"--user-agent={random.choice(UAS)}",
                    f"--window-size={1200 + random.randint(0,100)},{800 + random.randint(0,100)}"
                ]
            )
            # Give it a tiny bit to map hooks
            await asyncio.sleep(1)

        # Ensure page exists
        if not self.page:
            if url:
                self.page = await self.browser.get(url)
            else:
                self.page = await self.browser.get("about:blank")
            await asyncio.sleep(wait)
        elif action in ["goto", "read", "screenshot_and_analyze"] and url:
            await self.page.get(url)
            await asyncio.sleep(wait)

        output = display = ""

        try:
            if action == "click_text" and target_text:
                elem = await self.page.find(target_text, best_match=True)
                if elem: 
                    # HUMAN HEURISTICS: Move Mouse to element and hover
                    center = elem.attrs.get("center", [0, 0])
                    tx, ty = center
                    # Randomize a bit within the element
                    tx += random.randint(-5, 5)
                    ty += random.randint(-5, 5)
                    
                    await self.page.mouse_move(tx, ty)
                    await asyncio.sleep(0.3 + random.random() * 0.4) # Hover
                    
                    await elem.click()
                    await asyncio.sleep(wait)
                    display = f"Clicked text: '{target_text}' at [{tx}, {ty}]"
                else:
                    display = f"Text not found: '{target_text}'"

            elif action == "type_text" and target_text:
                elem = await self.page.find(target_text, best_match=True)
                if elem:
                    # HUMAN HEURISTICS: Move Mouse to element and hover before typing
                    center = elem.attrs.get("center", [0, 0])
                    tx, ty = center
                    await self.page.mouse_move(tx, ty)
                    await asyncio.sleep(0.3)
                    
                    await elem.click() # focus it
                    await asyncio.sleep(0.5)
                    # HUMAN TYPING: Type character-by-character with random delays
                    for char in input_text:
                        await elem.send_keys(char)
                        await asyncio.sleep(0.05 + random.random() * 0.1)
                    await asyncio.sleep(0.5)
                    display = f"Typed '{input_text}' (human-speed) near '{target_text}'"
                else:
                    display = f"Text not found for typing: '{target_text}'"

            elif action == "press_key":
                await self.page.keyboard.press(keys)
                await asyncio.sleep(wait)
                display = f"Pressed key: {keys}"

            elif action == "scroll":
                await self.page.scroll_down(800)
                await asyncio.sleep(1)
                display = "Scrolled down."

            elif action == "screenshot":
                path = f"/tmp/browse_{int(time.time())}.png"
                await self.page.save_screenshot(path)
                display = f"Screenshot saved: {path}"

            elif action == "screenshot_and_analyze":
                path = f"/tmp/browse_{int(time.time())}.png"
                await self.page.save_screenshot(path)
                from core.vision import vision
                prompt = args.get("prompt", "Describe the layout and contents of this web page in detail.")
                analysis = await vision.analyze_image(path, prompt)
                display = f"Screenshot analyzed:\n{analysis}"

            # Always fetch the updated DOM state if interacting
            if action in ["click_text", "type_text", "press_key", "scroll", "goto", "read"]:
                html = await self.page.get_content()
                clean = _extract_readable(html, url or "current page")
                output = f"{display}\n\n[PAGE STATE AFTER ACTION]\n{clean}"
                display = output
            else:
                output = display

        except Exception as e:
            output = display = f"Browser action '{action}' failed: {e}"

        # Do NOT close browser in finally block!
        return output, display

    async def _tool_analyze_image(self, args: dict):
        path = args.get("path", "")
        prompt = args.get("prompt", "Describe what is in this image.")
        if not path:
            return "No path provided for image analysis.", "No path provided."
        from core.vision import vision
        analysis = await vision.analyze_image(path, prompt)
        return analysis, analysis

execution_engine = ExecutionEngine()
