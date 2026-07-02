#!/usr/bin/env bash

# Setup script for poridhioss ML FastAPI AWS project
# Configures GitHub organization settings

set -e

echo "🚀 poridhioss ML FastAPI AWS - GitHub Setup"
echo "============================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI (gh) is not installed${NC}"
    echo "Install it from: https://cli.github.com"
    exit 1
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git is not installed${NC}"
    exit 1
fi

echo -e "${BLUE}📋 Configuration Steps:${NC}"
echo ""

# Get repository info
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login' 2>/dev/null || echo "")
REPO_NAME=$(gh repo view --json name --jq '.name' 2>/dev/null || echo "")

if [ -z "$REPO_OWNER" ] || [ -z "$REPO_NAME" ]; then
    echo -e "${YELLOW}⚠️  Run this script from inside a GitHub repository${NC}"
    exit 1
fi

REPO="${REPO_OWNER}/${REPO_NAME}"
echo -e "${GREEN}✓${NC} Repository: $REPO"
echo ""

# Enable required status checks
echo -e "${BLUE}1️⃣  Enabling branch protection for 'main'...${NC}"
gh api repos/$REPO_OWNER/$REPO_NAME/branches/main/protection \
  --input /dev/null \
  -X PUT \
  -f enforce_admins=true \
  -f required_status_checks='{"strict":true,"contexts":["build","test","security"]}' \
  -f required_pull_request_reviews='{"dismiss_stale_reviews":true,"require_code_owner_reviews":true,"required_approving_review_count":1}' \
  2>/dev/null && echo -e "${GREEN}✓${NC} Branch protection enabled" || echo -e "${YELLOW}⚠️  Could not enable branch protection${NC}"

echo ""

# Enable Dependabot alerts
echo -e "${BLUE}2️⃣  Enabling Dependabot alerts...${NC}"
gh api repos/$REPO_OWNER/$REPO_NAME \
  -X PATCH \
  -f security_and_analysis='{"dependabot_security_updates":{"status":"enabled"},"secret_scanning":{"status":"enabled"}}' \
  2>/dev/null && echo -e "${GREEN}✓${NC} Dependabot enabled" || echo -e "${YELLOW}⚠️  Could not enable Dependabot${NC}"

echo ""

# Enable automatic delete of head branches
echo -e "${BLUE}3️⃣  Enabling auto-delete of head branches...${NC}"
gh api repos/$REPO_OWNER/$REPO_NAME \
  -X PATCH \
  -f delete_branch_on_merge=true \
  2>/dev/null && echo -e "${GREEN}✓${NC} Auto-delete enabled" || echo -e "${YELLOW}⚠️  Could not enable auto-delete${NC}"

echo ""

# Enable auto merge
echo -e "${BLUE}4️⃣  Enabling auto merge for PRs...${NC}"
gh api repos/$REPO_OWNER/$REPO_NAME \
  -X PATCH \
  -f allow_auto_merge=true \
  2>/dev/null && echo -e "${GREEN}✓${NC} Auto merge enabled" || echo -e "${YELLOW}⚠️  Could not enable auto merge${NC}"

echo ""

# Set up GitHub Pages (if applicable)
echo -e "${BLUE}5️⃣  Checking GitHub Pages configuration...${NC}"
gh api repos/$REPO_OWNER/$REPO_NAME/pages \
  2>/dev/null && echo -e "${GREEN}✓${NC} GitHub Pages configured" || echo -e "${YELLOW}⚠️  GitHub Pages not configured${NC}"

echo ""

# Create commit and push
echo -e "${BLUE}6️⃣  Committing GitHub configuration files...${NC}"
git add -A
git commit -m "chore: add poridhioss organization GitHub configuration

- Add CI/CD workflows (ci-cd.yml, code-quality.yml, deploy-aws.yml)
- Add release workflow
- Add GitHub organization standards and CODEOWNERS
- Add CONTRIBUTING.md and CODE_OF_CONDUCT.md
- Add SECURITY.md and ARCHITECTURE.md
- Add issue and PR templates
- Configure Dependabot for automated dependency updates
- Add .editorconfig and .gitattributes for consistency
- Update .gitignore for Python/Node.js/Docker projects" || echo -e "${YELLOW}⚠️  Nothing to commit${NC}"

echo ""

echo -e "${GREEN}✅ GitHub Configuration Complete!${NC}"
echo ""
echo -e "${BLUE}📝 Next Steps:${NC}"
echo "1. Review the GitHub workflows: .github/workflows/"
echo "2. Configure GitHub secrets in Settings → Secrets and variables"
echo "3. Set up CODEOWNERS in Settings → Code owners"
echo "4. Review branch protection rules: Settings → Branches"
echo "5. Customize organization standards in .github/ORGANIZATION_STANDARDS.md"
echo ""
echo -e "${BLUE}🔗 Useful Links:${NC}"
echo "- Repository: https://github.com/$REPO"
echo "- Settings: https://github.com/$REPO/settings"
echo "- Actions: https://github.com/$REPO/actions"
echo "- Security: https://github.com/$REPO/security"
echo ""
echo -e "${YELLOW}💡 Tip: Create GitHub Actions secrets for:${NC}"
echo "   - AWS_ACCOUNT_ID"
echo "   - AWS_ROLE_TO_ASSUME"
echo "   - SONARCLOUD_TOKEN (for code quality)"
echo ""
