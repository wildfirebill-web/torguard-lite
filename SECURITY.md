# SECURITY.md for torguard-lite

## Reporting a Vulnerability

We appreciate your efforts in helping us maintain the security of our project, `torguard-lite`. If you discover any vulnerabilities or potential security issues, please report them to us as soon as possible. You can submit your findings through email at [security@torguard.com](mailto:security@torguard.com).

When reporting a vulnerability, please provide the following information:

- A detailed description of the issue
- Steps to reproduce the problem
- Any relevant code snippets or logs
- The affected version of `torguard-lite` and its dependencies
- Whether the issue is considered low, medium, high, or critical severity

## Responsible Disclosure

We value the security community and encourage responsible reporting and disclosure. We ask that you refrain from disclosing vulnerabilities to the public until they have been addressed by our team. We will respond to your report within a reasonable timeframe and keep you informed about the progress of addressing the issue.

## Scope

This document applies to the `torguard-lite` Python CLI tool for Torguard VPN management. The scope includes:

- The main `torguard-lite` source code
- Dependencies listed in `requirements.txt` or managed by pip
- Any other components directly related to the project's functionality

## Supported Versions

We support the latest major release of `torguard-lite` and the two preceding minor releases. For instance, if the latest major release is v1.3, we will also support v1.2 and v1.1. It is essential to ensure that your environment matches one of these supported versions when reporting vulnerabilities or seeking assistance.

## Dependency Scanning

To maintain a secure environment for `torguard-lite`, it's crucial to regularly scan its dependencies for known vulnerabilities using tools such as Snyk, WhiteSource, or Black Duck. We recommend running these scans before each release and addressing any discovered issues promptly.

## Commit Signing Requirements

To enhance the integrity and authenticity of our project's codebase, we require that all commit messages are signed using GPG. To set up GPG signing for your commits, follow the steps below:

1. Install GPG (GnuPG) on your system if it isn't already installed. On Ubuntu/Debian, you can use `sudo apt-get install gnupg` or `sudo apt install gnupg`. On macOS, you can use Homebrew: `brew install gpg`.

2. Create a new GPG key by running the following command:
   ```
   gpg --gen-key
   ```
   During the key creation process, make sure to provide a strong passphrase for your key.

3. Import your public key to the project's keyserver:
   ```
   gpg --keyserver hkp://keys.gnupg.net --send-keys <YOUR_PUBLIC_KEY_ID>
   ```

4. Export your public key in ASCII format and add it to your GitHub account's SSH keys:
   ```
   gpg --armor --export <YOUR_USERNAME> > ~/.ssh/id_rsa.pub.asc
   ```
   Then, copy the contents of `id_rsa.pub.asc` and add it to your GitHub account's SSH keys under Settings -> SSH and GPG keys -> New GPG key.

5. Configure Git to sign commits with your GPG key:
   ```
   git config --global user.signingkey <YOUR_PUBLIC_KEY_ID>
   ```

6. Set up Git to automatically verify the signature of each commit before pushing:
   ```
   git config --global commit.gpgsign true
   ```

By following these steps, you will ensure that your commits are signed and verified, contributing to the overall security and trustworthiness of the `torguard-lite` project.