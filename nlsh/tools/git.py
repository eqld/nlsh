"""
Git repository information tool.

This module provides a tool for gathering information about the current Git repository.
"""

import os
import subprocess
from typing import List, Optional

from nlsh.tools.base import BaseTool


class GitRepoInfo(BaseTool):
    """Provides information about the current Git repository."""
    
    def get_context(self):
        """Get Git repository information.
        
        Returns:
            str: Formatted Git repository information.
        """
        # Check if we're in a Git repository
        if not self._is_git_repo():
            return "Not a Git repository."
        
        result = ["Git Repository Information:"]
        
        # Get repository information
        repo_info = self._get_repo_info()
        if repo_info:
            result.append(f"Repository: {repo_info}")
        
        # Get current branch
        branch = self._get_current_branch()
        if branch:
            result.append(f"Current Branch: {branch}")
        
        # Get remote information
        remotes = self._get_remotes()
        if remotes:
            result.append("Remotes:")
            for remote in remotes:
                result.append(f"- {remote}")
        
        # Get recent commits
        commits = self._get_recent_commits()
        if commits:
            result.append("\nRecent Commits:")
            for commit in commits:
                result.append(f"- {commit}")
        
        # Get modified files
        modified = self._get_modified_files()
        if modified:
            result.append("\nModified Files:")
            for file in modified:
                result.append(f"- {file}")
        
        # Get tags
        tags = self._get_tags()
        if tags:
            result.append("\nTags:")
            for tag in tags:
                result.append(f"- {tag}")
        
        return "\n".join(result)
    
    def _is_git_repo(self) -> bool:
        """Check if the current directory is a Git repository.
        
        Returns:
            bool: True if the current directory is a Git repository, False otherwise.
        """
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _get_repo_info(self) -> Optional[str]:
        """Get repository name and path.
        
        Returns:
            str: Repository name and path, or None if not available.
        """
        try:
            # Get the repository root directory
            root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            ).stdout.strip()
            
            # Get the repository name (the directory name)
            repo_name = os.path.basename(root)
            
            return f"{repo_name} ({root})"
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
    
    def _get_current_branch(self) -> Optional[str]:
        """Get the current branch name.
        
        Returns:
            str: Current branch name, or None if not available.
        """
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            ).stdout.strip()
            
            return branch
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
    
    def _get_remotes(self) -> List[str]:
        """Get remote repository information.
        
        Returns:
            list: List of remote repository information strings.
        """
        try:
            # Get remote names
            remote_names = subprocess.run(
                ["git", "remote"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            ).stdout.strip().split("\n")
            
            # Filter out empty lines
            remote_names = [name for name in remote_names if name]
            
            # Get remote URLs
            remotes = []
            for name in remote_names:
                url = subprocess.run(
                    ["git", "remote", "get-url", name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True
                ).stdout.strip()
                
                remotes.append(f"{name}: {url}")
            
            return remotes
        except (subprocess.SubprocessError, FileNotFoundError):
            return []
    
    def _get_recent_commits(self, count=5) -> List[str]:
        """Get recent commits.
        
        Args:
            count: Number of recent commits to get.
            
        Returns:
            list: List of recent commit information strings.
        """
        try:
            # Get recent commits
            commits = subprocess.run(
                ["git", "log", f"-{count}", "--oneline"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            ).stdout.strip().split("\n")
            
            # Filter out empty lines
            commits = [commit for commit in commits if commit]
            
            return commits
        except (subprocess.SubprocessError, FileNotFoundError):
            return []
    
    def _get_modified_files(self) -> List[str]:
        """Get modified files.
        
        Returns:
            list: List of modified file paths.
        """
        try:
            # Get modified files
            modified = subprocess.run(
                ["git", "status", "--porcelain"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            ).stdout.strip().split("\n")
            
            # Filter out empty lines and format the output
            modified = [line for line in modified if line]
            formatted = []
            for line in modified:
                if line:
                    status = line[:2].strip()
                    file_path = line[3:].strip()
                    formatted.append(f"{file_path} ({status})")
            
            return formatted
        except (subprocess.SubprocessError, FileNotFoundError):
            return []
    
    def _get_tags(self) -> List[str]:
        """Get tags.
        
        Returns:
            list: List of tag names.
        """
        try:
            # Get tags
            tags = subprocess.run(
                ["git", "tag"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            ).stdout.strip().split("\n")
            
            # Filter out empty lines
            tags = [tag for tag in tags if tag]
            
            return tags
        except (subprocess.SubprocessError, FileNotFoundError):
            return []
