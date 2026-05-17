/*
test
*/

import <"g.stdio">

func banner() {
    stdio.printf("\n\n")
    stdio.printf("  ██████╗ ██╗")
    stdio.printf(" ██╔════╝ ██║")
    stdio.printf(" ██║  ███╗██║")
    stdio.printf(" ██║   ██║██║")
    stdio.printf(" ╚██████╔╝████████╗")
    stdio.printf("  ╚═════╝ ╚═══════╝   G Language Interpreted v0.2 | glangs first program. \n\n\n")
}

banner()

while(true) {
    let reader = stdio.readl("user >> ")

    if (reader == "banner") {
        printl("\n")
        printl("  ██████╗ ██╗")
        printl(" ██╔════╝ ██║")
        printl(" ██║  ███╗██║")
        printl(" ██║   ██║██║")
        printl(" ╚██████╔╝██║")
        printl("  ╚═════╝ ╚═╝   G Language Interpreted v0.2 | glangs first program. \n\n\n")
        printl("")
    }
    elif (reader == "clear") {
        system("clear")
    }
    elif (reader == "clear") {
        stdio.exec("clear")
    }
}