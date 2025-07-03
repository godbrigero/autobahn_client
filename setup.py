#!/usr/bin/env python3
"""Setup script for autobahn_client."""

import os
import subprocess
from setuptools import setup, find_packages, Command


class ProtocCommand(Command):
    """Custom command to run protoc compiler using make."""
    description = "run protoc compiler via make"
    user_options = []
    
    def initialize_options(self):
        pass
        
    def finalize_options(self):
        pass
    
    def run(self):
        command = ["make", "protoc"]
        self.announce("Running command: %s" % " ".join(command), level=2)
        subprocess.check_call(command)


if __name__ == "__main__":
    setup(
        packages=find_packages(),
        cmdclass={
            'protoc': ProtocCommand,
        },
    )