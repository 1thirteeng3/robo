"""Obsidian Vault Integration Tool."""

import os
import re
from pathlib import Path
from typing import Any
from loguru import logger

from nanobot.agent.tools.base import Tool


class ObsidianTool(Tool):
    """Tool to write markdown notes directly to the Obsidian Vault."""

    def __init__(self, vault_path: Path | str | None = None):
        # Allow vault path to be explicitly passed, or loaded from an environment variable.
        # Fallback to a default 'Vault' directory in the user's home path if none provided.
        env_vault = os.environ.get("OBSIDIAN_VAULT_PATH")
        if vault_path:
            self._vault_dir = Path(vault_path)
        elif env_vault:
            self._vault_dir = Path(env_vault)
        else:
            self._vault_dir = Path.home() / "Documents" / "Vault"

        try:
            self._vault_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create vault directory at {self._vault_dir}: {e}")

    @property
    def name(self) -> str:
        return "obsidian_write"

    @property
    def description(self) -> str:
        return "Write generated markdown content directly to the local Obsidian Vault."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string", 
                    "description": "The name of the file to create or overwrite (without path)."
                },
                "content": {
                    "type": "string", 
                    "description": "The markdown content to write, including Frontmatter YAML if requested."
                },
            },
            "required": ["filename", "content"],
        }

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes filename for cross-platform compatibility."""
        # Remove directory traversal
        filename = os.path.basename(filename)
        # Convert spaces to hyphens (optional but good practice) or simply strip bad chars
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        if not filename.endswith(".md"):
            filename += ".md"
        return filename

    async def execute(self, filename: str, content: str, **kwargs: Any) -> str:
        import aiofiles
        
        try:
            clean_name = self._sanitize_filename(filename)
            file_path = self._vault_dir / clean_name
            
            # Ensure the directory exists (in case the base directory wasn't ready)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(file_path, 'w', encoding="utf-8") as f:
                await f.write(content)
            
            logger.info(f"ObsidianTool: Wrote to {file_path}")
            return f"Successfully wrote note '{clean_name}' to Obsidian Vault at {self._vault_dir}"
            
        except PermissionError as e:
            return f"PermissionError writing to Obsidian vault: {e}"
        except Exception as e:
            return f"Error writing file to Obsidian vault: {str(e)}"
