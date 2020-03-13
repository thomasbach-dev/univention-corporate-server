BEGIN {
	printf("# %s\n", ARGV[1])
    print ":source-highlighter: prettify"
    print ""

    preamble = "# -*- coding: utf-8 -*-"                                    \
        "\n" "import univention.config_registry"                            \
        "\n" "configRegistry = univention.config_registry.ConfigRegistry()" \
        "\n" "configRegistry.load()"                                        \
        "\n" "# for compatibility"                                          \
        "\n" "baseConfig = configRegistry"
}
END {
	print converted > "/tmp/convert-target.py"

    print "### Code changes"
    print "[source,diff]"
    print "-------------"
	if (system("diff -y --suppress-common-lines " FILENAME " /tmp/convert-target.py") != 0) {
        print ""
        print "[!] file changed"
        print ""
		# replace original file only if it has changed...
        print converted > FILENAME
        close(FILENAME)
	}
    print "-------------"

    # exit...
    exit err
}
# if start is 0 and we found a @!@-line: set start
!start && /@!@/ { start = 1 ; converted = converted $0 ; next }
# if start is set (and we still are within a code section) and there comes a @!@
start && /@!@/ {
	if (code2 != "") {
		print code2 > "/tmp/convert-tmp.py" ; close("/tmp/convert-tmp.py")
		system("2to3-2.7 --no-diffs -w /tmp/convert-tmp.py 2>/dev/null")
		cmd = "cat /tmp/convert-tmp.py"
		while ((cmd | getline result) > 0) {
			code3 = code3 result "\n"
		}
		close(cmd)

		print preamble "\n" code2 > "/tmp/convert-py2.py" ; close("/tmp/convert-py2.py")
		print preamble "\n" code3 > "/tmp/convert-py3.py" ; close("/tmp/convert-py3.py")


		if (system("scp -q /tmp/convert-py[23].py  testsystem:/tmp/") == 0)
		{
            print "### Difference when running the converted script with python2"
            print "[source,diff]"
            print "-------------"
            if (system("ssh -q testsystem 'diff -y --suppress-common-lines <(python2 /tmp/convert-py2.py 2>&1) <(python2 /tmp/convert-py3.py 2>&1)'") != 0)
            { err = err + 1 }
            print "-------------"
            print ""
            print "### Difference between python2 output and python3 output"
            print "[source,diff]"
            print "-------------"
            if (system("ssh -q testsystem 'diff -y --suppress-common-lines <(python2 /tmp/convert-py2.py 2>&1) <(python3 /tmp/convert-py3.py 2>&1)'") != 0)
            { err = err + 1 }
            print "-------------"
        }
		else
		{ err = 127 }

		converted = converted code3 $0
	} else {
		converted = converted $0
	}

	# if (system("ssh testsystem python3 /tmp/convert-py2.py 2>/dev/null 1>/dev/null") != 0) {
	# } else {
	# 	converted = converted code2 "\n" $0
	# }
	code3 = ""
	code2 = ""
	next
}
# if start is set and we have not yet found its end: append line to the code
# variable and increment the code line counter
start { code2 = code2 "\n" $0 ; lines++ ; next }
# everything else will be passed into the variable

NR==1 { converted = $0 "\n" ; next }
{ converted = converted "\n" $0 }

