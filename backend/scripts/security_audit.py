#!/usr/bin/env python3
"""
Security audit script for NouxCubeIA
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security_validator import SecurityValidator

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def run_security_audit():
    """Run comprehensive security audit"""
    print("🔒 NouxCubeIA Security Audit")
    print("=" * 50)

    validator = SecurityValidator()
    result = validator.validate_all()

    # Print results
    print(f"\n📊 Security Score: {result['security_score']}/100")

    if result['errors']:
        print(f"\n❌ Critical Issues ({len(result['errors'])}):")
        for error in result['errors']:
            print(f"  • {error}")

    if result['warnings']:
        print(f"\n⚠️ Warnings ({len(result['warnings'])}):")
        for warning in result['warnings']:
            print(f"  • {warning}")

    print(f"\n💡 Recommendations ({len(result['recommendations'])}):")
    for rec in result['recommendations']:
        print(f"  • {rec}")

    # Environment info
    print("
🔧 Environment Information:"    print(f"  • Debug Mode: {settings.DEBUG}")
    print(f"  • Environment: {'Development' if settings.DEBUG else 'Production'}")
    print(f"  • Database: {settings.POSTGRES_SERVER}")
    print(f"  • CORS Origins: {len([str(o) for o in settings.BACKEND_CORS_ORIGINS])} configured")

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "security_score": result['security_score'],
        "errors": result['errors'],
        "warnings": result['warnings'],
        "recommendations": result['recommendations'],
        "environment": {
            "debug": settings.DEBUG,
            "database_host": settings.POSTGRES_SERVER,
            "cors_origins_count": len([str(o) for o in settings.BACKEND_CORS_ORIGINS])
        }
    }

    report_file = Path("security_audit_report.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Report saved to: {report_file}")

    # Exit with appropriate code
    if result['errors']:
        print("\n❌ Security audit FAILED - fix critical issues before deployment!")
        sys.exit(1)
    else:
        print("\n✅ Security audit PASSED")
        sys.exit(0)


if __name__ == "__main__":
    run_security_audit()