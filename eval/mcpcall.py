"""Call one mri-preread MCP tool over stdio: python mcpcall.py <study> <tool> '<json args>' <out-prefix>
Text results are printed, images saved as <out-prefix>_<n>.png."""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
study, tool, args = sys.argv[1], sys.argv[2], json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")
out = sys.argv[4] if len(sys.argv) > 4 else "/tmp/mcp_out"


async def main():
    p = StdioServerParameters(command=f"{R}/.venv/bin/mri-preread", args=["serve", study],
                              env={**os.environ, "BRAIN_VIEWER_PORT": os.environ.get("BRAIN_VIEWER_PORT", "8791")})
    async with stdio_client(p, errlog=open(os.devnull, "w")) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            if tool == "_instructions": print(init.instructions); return
            res = await s.call_tool(tool, args)
            n = 0
            for c in res.content:
                if c.type == "text": print(c.text)
                elif c.type == "image":
                    import base64
                    n += 1; f = f"{out}_{n}.png"; open(f, "wb").write(base64.b64decode(c.data)); print("IMAGE:", f)

asyncio.run(main())
