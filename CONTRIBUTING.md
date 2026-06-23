# Contributing Guide

Thank you for your interest in contributing to TorGuard Lite! This project is a Python GUI for managing TorGuard VPN connections, and we're excited that you want to help. Please follow the guidelines below.

## Reporting Bugs

If you encounter any issues or bugs while using Torguard-Lite, please open a new issue in this repository with a detailed description of the problem, including:

1. The version number of Torguard-Lite that you are using.
2. Steps to reproduce the bug.
3. Expected behavior versus actual behavior.
4. Any relevant error messages or logs.

## Feature Request Process

If you have an idea for a new feature or improvement, please open an issue with a clear title and description of your proposal. Be sure to provide any rationale, use cases, or potential benefits for the proposed feature. We will consider all feature requests and prioritize them based on their impact and feasibility.

## Pull Request Workflow

1. Fork this repository and create a new branch for your changes: `git checkout -b feature/your-feature-name`.
2. Make your changes, ensuring that the code adheres to our coding standards (see below).
3. Run tests to ensure your changes don't introduce any new issues.
4. Commit your changes with descriptive commit messages (see below).
5. Push your branch to your forked repository: `git push origin feature/your-feature-name`.
6. Submit a pull request to the main Torguard-Lite repository.
7. We will review your PR and may provide feedback or requests for changes.

## Coding Standards (Python)

1. Use consistent naming conventions for functions, variables, and classes.
2. Follow PEP 8 style guide for Python code formatting.
3. Write clear, concise, and well-documented code.
4. Use appropriate comments to explain complex logic or potential issues.
5. Keep the code modular and easy to read.

## Commit Message Format

Commit messages should be concise, descriptive, and follow this format:

```
[Type](optional scope): Short summary of the change

Detailed description of the change or motivation for the change, if necessary.

Issue number(s) if relevant
```

Example commit message:

```
feat: Add support for TorGuard account creation

This commit adds functionality to create new TorGuard accounts using the CLI.

Issue #123
```

## Test Requirements

For each pull request, we require passing tests in our testing suite to ensure that changes don't negatively impact existing functionality. Please make sure you have all the necessary dependencies installed and run the test suite before submitting your PR.

We appreciate your contributions to Torguard-Lite! If you have any questions or need assistance, please don't hesitate to reach out. Happy coding!