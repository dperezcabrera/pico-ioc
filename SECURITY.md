# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.2.x   | Yes       |
| < 2.2   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in pico-ioc, please report it responsibly:

1. **Do NOT open a public GitHub issue.**
2. Email **dperezcabrera@gmail.com** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. You will receive an acknowledgment within **48 hours**.
4. A fix will be prioritized and released as a patch version.

## Scope

pico-ioc is a dependency injection library with zero runtime dependencies. Its attack surface is limited to:

- Code execution via component instantiation and AOP interceptors
- Configuration deserialization (YAML, JSON, environment variables)
- Event bus dispatch
