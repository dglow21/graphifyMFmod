      *================================================================
      * SAMPLE2 - exercises AUTHOR comment entry, embedded SQL, CICS,
      * GO TO, and dynamic CALL. Fixed format.
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SAMPLE2.
       AUTHOR. JANE DEVELOPER.
       INSTALLATION. ACME CORP MAINFRAME SYSTEMS.
       DATE-WRITTEN. 2024-01-15.
       DATE-COMPILED.
       REMARKS. THIS PROGRAM POSTS CUSTOMER ORDERS.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           EXEC SQL INCLUDE SQLCA END-EXEC.
           EXEC SQL INCLUDE CUSTROW END-EXEC.
       01 WS-CUST-ID    PIC 9(8).
       01 WS-CUST-NAME  PIC X(30).
       01 WS-RC         PIC S9(4) COMP.
       PROCEDURE DIVISION.
       0000-MAIN SECTION.
       0100-INIT.
           MOVE ZERO TO WS-RC.
           PERFORM 0200-FETCH-CUST.
           PERFORM 0300-POST THRU 0300-EXIT.
           GOBACK.
       0200-FETCH-CUST.
           EXEC SQL
               SELECT CUST_NAME
                 INTO :WS-CUST-NAME
                 FROM ACMEDB.CUSTOMER_TBL C
                 JOIN ACMEDB.ACCOUNT_TBL A
                   ON C.CUST_ID = A.CUST_ID
                WHERE C.CUST_ID = :WS-CUST-ID
           END-EXEC.
           IF SQLCODE NOT = 0 GO TO 0999-ERROR.
       0300-POST.
           EXEC CICS LINK PROGRAM('POSTPGM')
                COMMAREA(WS-CUST-ID) END-EXEC.
           EXEC SQL
               UPDATE ACMEDB.CUSTOMER_TBL
                  SET LAST_POST = CURRENT DATE
                WHERE CUST_ID = :WS-CUST-ID
           END-EXEC.
           EXEC CICS SEND MAP('CONFMAP') MAPSET('CONFSET') END-EXEC.
           DISPLAY 'PLEASE CALL SUPPORT IF THIS FAILS'.
           CALL 'AUDITLOG' USING WS-CUST-ID.
       0300-EXIT.
           EXIT.
       0999-ERROR.
           MOVE 16 TO RETURN-CODE.
           GOBACK.
