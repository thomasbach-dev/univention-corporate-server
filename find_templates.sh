#!/bin/bash

REPO_PATH=${1:-`pwd`}
CONVERTER=2to3-2.7
PYTHONPATH=`pwd`/base/univention-config-registry/python/



create_table() {
    for FILE in $(grep -l --include '*.conf' -o  -r '@!@' $REPO_PATH  | sort); do
        PYTHON2_EXEC=`sed -n '/^@!@$/,/^@!@/{/^@!@/d; p}' $FILE | (echo 'from univention.config_registry import ConfigRegistry' ; echo 'configRegistry = ConfigRegistry("sample_config")' ; echo 'baseConfig = configRegistry' ; cat -) | python2 1>/dev/null 2>/dev/null && echo "✅" || echo "❌"`
        PYTHON3_EXEC=`sed -n '/^@!@$/,/^@!@/{/^@!@/d; p}' $FILE | (echo 'from univention.config_registry import ConfigRegistry' ; echo 'configRegistry = ConfigRegistry("sample_config")' ; echo 'baseConfig = configRegistry' ; cat -) | python3 1>/dev/null 2>/dev/null && echo "✅" || echo "❌"`
        DIFF3_APPROX=`sed -n '/^@!@$/,/^@!@/{/^@!@/d; p}' $FILE | $CONVERTER - 2>/dev/null | diffstat -sm | cut -f2 -d','`
        printf "|%s | %s | %s | %s\n" "$DIFF3_APPROX" "$PYTHON2_EXEC" "$PYTHON3_EXEC" "$FILE"
    done
}

create_table | sort -n -t '|' -k 2 |
(
    echo '[cols="2,1,1,3"]';
    echo '|===';
    echo '| 2to3 | python2 | python3 | filename';
    cat -
) | tee output.md | asciidoctor -o output.html -

