* Sample HLASM program
MYPROG   CSECT
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         CALL  SUBRTN1,(PARMLIST),VL
         LINK  EP=SUBRTN2,PARAM=(A,B)
         L     15,=V(EXTSUB3)
         BALR  14,15
         COPY  MYMACROS
         EXTRN EXTSUB4,EXTSUB5
         ENTRY MYPROG2
PARMLIST DC    A(0)
MYPROG2  DS    0H
         BR    14
WORKAREA DSECT
FIELD1   DS    CL8
         END   MYPROG

         MACRO
&LBL     MYMAC &P1,&P2
&LBL     DS    0H
         MEND
