# Security Policy

## Scope

NutriLens is a read-heavy tool that extracts publicly visible product information from e-commerce pages. There is no user authentication, no payment processing, and no private user data stored.

That said, we take security seriously. The admin dashboard is publicly accessible by design — it stores only product nutrition data, not personal information.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email: **security@nutrilens.dev** (or open a private security advisory via GitHub's "Report a vulnerability" button on the Security tab).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Your suggested fix (optional but appreciated)

We will acknowledge within 48 hours and aim to ship a fix within 7 days for critical issues.

## What is NOT in scope

- Extracting data from Amazon/BigBasket/Flipkart that is already publicly visible — this is the intended function of the extension
- The `/admin` dashboard being publicly readable — this is intentional (transparency)
- Rate limits on the API in development mode

## What IS in scope

- SQL injection via any API endpoint
- SSRF via the OCR service image URL processing
- XSS in the admin dashboard HTML
- Remote code execution in the Celery worker
- Admin dashboard being writable without authentication in production deployments
