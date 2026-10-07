import glob
import os
import platform
import shutil
import subprocess
from typing import Optional


REMOTION_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "remotion-src"))
OUTPUT_DIR = "outputs"


def _ensure_remotion_deps(log=print) -> None:
    """Install remotion-src deps if node_modules/.bin/remotion is missing."""
    remotion_bin = os.path.join(REMOTION_SRC, "node_modules", ".bin", "remotion")
    if os.path.exists(remotion_bin):
        return
    log("  📦 Installing Remotion dependencies (first run)...")
    subprocess.run(
        ["npm", "install"],
        cwd=REMOTION_SRC,
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if not os.path.exists(remotion_bin):
        raise RuntimeError(
            "Remotion CLI not found after npm install. "
            "Run: cd remotion-src && npm install"
        )


def _remotion_bin() -> str:
    return os.path.join(REMOTION_SRC, "node_modules", ".bin", "remotion")


def _find_remotion_chrome_shell() -> Optional[str]:
    pattern = os.path.join(
        REMOTION_SRC,
        "node_modules",
        ".remotion",
        "chrome-headless-shell",
        "**",
        "chrome-headless-shell",
    )
    matches = sorted(glob.glob(pattern, recursive=True))
    # Prefer executable files (mac/linux binary, not .exe on unix)
    for path in matches:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            # skip Windows .exe on non-Windows
            if platform.system() != "Windows" and path.endswith(".exe"):
                continue
            return path
    # Windows
    win_matches = sorted(
        glob.glob(
            os.path.join(
                REMOTION_SRC,
                "node_modules",
                ".remotion",
                "chrome-headless-shell",
                "**",
                "chrome-headless-shell.exe",
            ),
            recursive=True,
        )
    )
    for path in win_matches:
        if os.path.isfile(path):
            return path
    return None


def _ensure_browser(log=print) -> Optional[str]:
    """
    Prefer Remotion's bundled Chrome Headless Shell.
    Fall back to system Chrome only if shell is unavailable.
    """
    shell = _find_remotion_chrome_shell()
    if shell:
        return shell

    log("  ⬇️ Downloading Remotion Chrome Headless Shell (first run)...")
    try:
        subprocess.run(
            [_remotion_bin(), "browser", "ensure"],
            cwd=REMOTION_SRC,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except Exception as e:
        log(f"  ⚠️ browser ensure failed: {e}")

    shell = _find_remotion_chrome_shell()
    if shell:
        return shell

    # Fallback: system browsers
    env_chrome = os.getenv("PUPPETEER_EXECUTABLE_PATH") or os.getenv("CHROME_BIN")
    if env_chrome and os.path.exists(env_chrome):
        return env_chrome

    candidates: list[str] = []
    system = platform.system()
    if system == "Darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    elif system == "Linux":
        candidates.extend(
            [
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome",
            ]
        )

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _sanitize_tsx(tsx_code: str) -> str:
    import re

    code = (tsx_code or "").strip()
    fence = re.search(r"```(?:typescript|tsx|ts|js|jsx)?\s*\n([\s\S]*?)```", code)
    if fence:
        code = fence.group(1).strip()
    else:
        code = re.sub(
            r"^```(?:typescript|tsx|ts|js|jsx)?\s*\n?",
            "",
            code,
            flags=re.MULTILINE,
        )
        code = re.sub(r"\n?```\s*$", "", code)

    m = re.search(r"(?m)^(import |export |const |function |type )", code)
    if m and m.start() > 0:
        code = code[m.start() :]

    if "from 'react'" not in code and 'from "react"' not in code:
        code = "import React from 'react';\n" + code
    if "MainComposition" not in code:
        raise RuntimeError("Generated Remotion code missing MainComposition export")
    code = re.sub(r"export\s+default\s+MainComposition;?", "", code)
    code = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", code)
    code = code.replace("lowest:", "0,")
    return code.strip()


def render_remotion(
    tsx_code: str,
    job_id: str,
    duration: int = 60,
    output_dir: str = OUTPUT_DIR,
    log=print,
) -> tuple[Optional[str], Optional[str]]:
    """
    Write generated MainComposition.tsx into remotion-src and render via Remotion CLI.
    Returns (video_path, error).
    """
    try:
        _ensure_remotion_deps(log=log)
    except Exception as e:
        return None, f"Failed to install Remotion deps: {e}"

    os.makedirs(output_dir, exist_ok=True)
    compositions_dir = os.path.join(REMOTION_SRC, "src", "compositions")
    job_comp_dir = os.path.join(compositions_dir, f"job_{job_id}")
    try:
        tsx_code = _sanitize_tsx(tsx_code)
    except Exception as e:
        return None, str(e)

    os.makedirs(job_comp_dir, exist_ok=True)
    try:
        return _render_job(tsx_code, job_id, job_comp_dir, duration, output_dir, log)
    finally:
        _restore_root(job_comp_dir)


def _render_job(
    tsx_code: str,
    job_id: str,
    job_comp_dir: str,
    duration: int,
    output_dir: str,
    log,
) -> tuple[Optional[str], Optional[str]]:
    component_path = os.path.join(job_comp_dir, "MainComposition.tsx")
    with open(component_path, "w", encoding="utf-8") as f:
        f.write(tsx_code)

    # Align with API max (180s); keep a floor for short clips
    duration = max(15, min(int(duration), 180))
    frames = duration * 30

    root_path = os.path.join(REMOTION_SRC, "src", "Root.tsx")
    with open(root_path, "w", encoding="utf-8") as f:
        f.write(
            f"""import React from 'react';
import {{Composition}} from 'remotion';
import {{MainComposition}} from './compositions/job_{job_id}/MainComposition';

export const RemotionRoot: React.FC = () => {{
  return (
    <Composition
      id="MainVideo"
      component={{MainComposition}}
      durationInFrames={{{frames}}}
      fps={{30}}
      width={{1920}}
      height={{1080}}
      defaultProps={{{{ topic: "video" }}}}
    />
  );
}};
"""
        )

    output_path = os.path.abspath(os.path.join(output_dir, f"{job_id}_remotion.mp4"))
    remotion_bin = _remotion_bin()
    browser = _ensure_browser(log=log)

    cmd = [
        remotion_bin,
        "render",
        "src/index.ts",
        "MainVideo",
        output_path,
        "--log=error",
        "--concurrency=1",
    ]
    if browser:
        cmd.extend(["--browser-executable", browser])
        log(f"  🌐 Using browser: {browser}")
    else:
        return None, (
            "No Remotion Chrome Headless Shell or system Chrome found. "
            "Run: cd remotion-src && npx remotion browser ensure"
        )

    env = os.environ.copy()
    env["PUPPETEER_EXECUTABLE_PATH"] = browser
    env["CHROME_BIN"] = browser

    try:
        log(f"  ▶️ Remotion render ({duration}s / {frames} frames)")
        subprocess.run(
            cmd,
            cwd=REMOTION_SRC,
            check=True,
            capture_output=True,
            text=True,
            timeout=900,
            env=env,
        )
    except subprocess.CalledProcessError as e:
        err = ((e.stderr or "") + "\n" + (e.stdout or "")).strip() or str(e)
        err_path = os.path.join(output_dir, f"{job_id}_remotion_error.log")
        with open(err_path, "w", encoding="utf-8") as f:
            f.write(err)
        log(f"  ❌ Remotion render failed. Log: {err_path}")
        return None, err
    except subprocess.TimeoutExpired:
        return None, "Remotion render timed out after 900s"

    if not os.path.exists(output_path):
        return None, "Remotion finished but output mp4 was not found"

    log(f"  ✔️ Remotion video at {output_path}")
    return output_path, None


def _restore_root(job_comp_dir: str) -> None:
    """Point Root.tsx back at a stable composition and drop the job folder."""
    root_path = os.path.join(REMOTION_SRC, "src", "Root.tsx")
    try:
        with open(root_path, "w", encoding="utf-8") as f:
            f.write(_STABLE_ROOT)
    except OSError:
        pass
    shutil.rmtree(job_comp_dir, ignore_errors=True)


_STABLE_ROOT = """import React from 'react';
import {AbsoluteFill, Composition, interpolate, useCurrentFrame} from 'remotion';

const FallbackComposition: React.FC<{topic?: string}> = ({topic}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#0B1020',
        color: 'white',
        justifyContent: 'center',
        alignItems: 'center',
        fontFamily: 'Inter, system-ui, sans-serif',
        opacity,
      }}
    >
      <h1 style={{fontSize: 64, margin: 0}}>{topic || 'Clarity Video'}</h1>
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MainVideo"
      component={FallbackComposition}
      durationInFrames={90}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{topic: 'Clarity Video'}}
    />
  );
};
"""
