#!/bin/bash
# Fix pr_check.sh secrets leak guard bug

sed -i '113s/|| echo "0"/|| true/' /root/Smart-Investment-stretegy/tools/pr_check.sh
sed -i '117s/|| echo "0"/|| true/' /root/Smart-Investment-stretegy/tools/pr_check.sh
sed -i '120s/!= "0"/> 0/g' /root/Smart-Investment-stretegy/tools/pr_check.sh

echo "Fixed pr_check.sh:"
echo "  - Line 113: Changed '|| echo \"0\"' to '|| true'"
echo "  - Line 117: Changed '|| echo \"0\"' to '|| true'"
echo "  - Line 120: Changed '!= \"0\"' to '> 0'"
echo ""
echo "These changes fix:"
echo "  1. Stop outputting extra '0' to stdout"
echo "  2. Use numeric comparison instead of string comparison"
