# Contributing to poridhioss ML FastAPI AWS

Thank you for your interest in contributing to our project! We welcome contributions from everyone in the poridhioss organization.

## Code of Conduct

We are committed to providing a welcoming and inclusive environment for all contributors. Please be respectful and constructive in all interactions.

## Getting Started

1. **Fork the repository** (within the poridhioss organization)
2. **Clone your fork locally**
   ```bash
   git clone https://github.com/poridhioss/ml-fastapi-aws.git
   cd ml-fastapi-aws
   ```

3. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Backend
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend
```bash
cd frontend
npm install
```

### Run Locally
```bash
docker-compose up --build
```

## Coding Standards

### Backend (Python)
- Follow [PEP 8](https://pep8.org/) style guide
- Use [Black](https://github.com/psf/black) for code formatting
- Use [isort](https://pycqa.github.io/isort/) for import sorting
- Write type hints for all functions
- Maintain test coverage above 80%

### Frontend (TypeScript/React)
- Follow [ESLint](https://eslint.org/) rules
- Use [Prettier](https://prettier.io/) for code formatting
- Write functional components with hooks
- Include JSDoc comments for complex functions

### General
- Use meaningful commit messages
- Keep commits atomic and focused
- Write clear, descriptive PR descriptions
- Add tests for new features
- Update documentation as needed

## Git Workflow

### Branch Naming
- Feature: `feature/short-description`
- Bugfix: `bugfix/short-description`
- Hotfix: `hotfix/short-description`
- Docs: `docs/short-description`

### Commit Messages
Use conventional commits format:
```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(prediction): add batch prediction endpoint

- Implemented bulk prediction processing
- Added request validation
- Includes unit tests

Closes #42
```

## Pull Request Process

1. **Update your branch** with the latest main
   ```bash
   git pull origin main
   ```

2. **Run tests locally**
   ```bash
   pytest tests/
   cd frontend && npm run test
   ```

3. **Push your branch**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request** with:
   - Clear title describing the changes
   - Detailed description of what and why
   - Link to related issues
   - Screenshots/videos if UI changes

5. **Respond to review comments** constructively

6. **Ensure CI/CD passes** before merging

## Testing Requirements

### Backend
- Unit tests for all functions
- Integration tests for API endpoints
- Test coverage minimum: 80%

```bash
pytest tests/ -v --cov
```

### Frontend
- Unit tests for components
- Integration tests for user flows

```bash
cd frontend && npm run test
```

## Documentation

- Update README.md for user-facing changes
- Update ARCHITECTURE.md for system changes
- Add JSDoc/docstrings for new functions
- Include inline comments for complex logic

## Issues and Discussions

- Check [existing issues](../../issues) before creating new ones
- Use issue templates provided
- Be descriptive and include reproduction steps for bugs
- Tag issues appropriately (bug, feature, documentation, etc.)

## Questions?

- Check [discussions](../../discussions) for Q&A
- Ask in the #development channel (Slack/Discord)
- Contact the maintainers: @poridhioss/maintainers

---

**Thank you for contributing!** 🎉
