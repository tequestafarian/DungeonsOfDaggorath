;
;  DODLOAD: CoCo 3 disk loader for Dungeons of Daggorath
;
;  Disk BASIC lives in RAM at $C000-$DFFF on a CoCo 3, so the 8K game
;  image can't be LOADMed there directly.  It is loaded at IMAGE and
;  this stub copies it up to $C000 once BASIC is no longer needed.
;
        pragma  6809

IMAGE   EQU     $5000           ;load addr of game image
ROMBAS  EQU     $C000           ;run addr of game image
ROMLEN  EQU     $2000           ;8K

        ORG     $4F00
START   ORCC    #$50            ;no interrupts while we rearrange memory
        LDA     #$CC            ;GIME: CoCo compatible, MMU on, $FExx const
        STA     $FF90           ;   .
        CLR     $FF98           ;GIME video: VDG compatible mode
        CLR     $FF99           ;   .
        CLR     $FF9A           ;border black
        STA     $FFD8           ;normal (0.89MHz) CPU speed
        STA     $FFDF           ;all-RAM map type
        LDX     #IMAGE          ;source
        LDU     #ROMBAS         ;destination
COPY    LDD     ,X++            ;move a word
        STD     ,U++            ;   .
        CMPX    #IMAGE+ROMLEN   ;done yet?
        BLO     COPY            ;   nope
        JMP     ROMBAS          ;cartridge entry (DEMO)

        ORG     IMAGE
        INCLUDEBIN ../build/dod.rom

        END     START
