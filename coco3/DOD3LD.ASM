;
;  DOD3LD: disk loader for the CoCo 3 edition (needs 512K)
;
;  LOADM does the heavy lifting.  Before each 8K asset block a
;  one-byte segment is "loaded" into MMU register $FFA2, so the block
;  that follows lands in that physical page ($00-$06) instead of the
;  usual one.  Disk BASIC never touches $4000-$5FFF, so this is safe
;  while it runs.  The game image itself is loaded at IMAGE and
;  copied up to $C000 once BASIC is no longer needed.
;
        pragma  6809

IMAGE   EQU     $4000           ;load addr of game image
ROMBAS  EQU     $C000           ;run addr of game image
MMUSL2  EQU     $FFA2           ;MMU task 0, $4000-$5FFF

ASSET   MACRO
        ORG     MMUSL2
        FCB     \1
        ORG     IMAGE
        INCLUDEBIN ../build/td_blk\2.bin
        ENDM

        ASSET   $00,00
        ASSET   $01,01
        ASSET   $02,02
        ASSET   $03,03
        ASSET   $04,04
        ASSET   $05,05
        ASSET   $06,06
        ORG     MMUSL2          ;back to the normal page
        FCB     $3A

        ORG     IMAGE-$100
START   ORCC    #$50            ;no interrupts while we rearrange memory
        STA     $FFDF           ;all-RAM map type
        LDX     #IMAGE          ;source
        LDU     #ROMBAS         ;destination
COPY    LDD     ,X++            ;move a word
        STD     ,U++            ;   .
        CMPX    #IMEND          ;done yet?
        BLO     COPY            ;   nope
        JMP     ROMBAS          ;cartridge entry (DEMO)

        ORG     IMAGE
        INCLUDEBIN ../build/dod3.rom
IMEND   EQU     *

        IFGT    IMEND-IMAGE-($FE00-ROMBAS)
        ERROR   "game image runs into the $FExx vector page"
        ENDC

        END     START
