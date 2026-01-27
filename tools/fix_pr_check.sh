#!/bin/bash
# Fix pr_check.sh secrets leak guard bug

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
target="$repo_root/tools/pr_check.sh"

sed -i '113s/|| echo "0"/|| true/' "$target"
sed -i '117s/|| echo "0"/|| true/' "$target"
sed -i '120s/!= "0"/> 0/g' "$target"

echo "Fixed pr_check.sh:"
echo "  - Line 113: Changed '|| echo \"0\"' to '|| true'"
echo "  - Line 117: Changed '|| echo \"0\"' to '|| true'"
echo "  - Line 120: Changed '!= \"0\"' to '> 0'"
echo ""
echo "These changes fix:"
echo "  1. Stop outputting extra '0' to stdout"
echo "  2. Use numeric comparison instead of string comparison"
