      * Sample COBOL copybook (record layout) for graphify tests.
       01 CUSTOMER-RECORD.
          05 CUST-ID            PIC 9(8).
          05 CUST-NAME          PIC X(30).
          05 CUST-BALANCE       PIC S9(7)V99 COMP-3.
       01 CUSTOMER-FLAGS.
          05 CUST-ACTIVE-FLAG   PIC X(1).
