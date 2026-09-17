**Requirement.txt**

this contain the list of dependencies along with their version.

**.env**

This file contains teh OpenAi Api Key and the database connection details.

**Script.sql**

Script.sql file contains the complete details of the table creation, including the structure of each table, such as the columns, data types, and constraints (like primary keys, default values, etc.). It also includes any additional rules, such as default values, constraints, and optimizations that apply to the tables, ensuring the database schema is properly set up and managed.

**Schema_expert**

This file contains an auto-generated schema profile for a database, specifically detailing metadata and statistics about database tables. It includes information about the columns of these tables, including data types, descriptions, distinct values, row counts, null percentages, and other attributes. This schema profile is used to analyze the structure of the database and can assist in optimizing queries, understanding data distributions, and ensuring consistency in the database schema.

**nm4_sql**

The file nm4_sql.py defines a class called SQLService, which is designed to assist in the generation, validation, and correction of SQL queries. It includes features such as detecting the language of SQL-related questions (Arabic or English), building schema context based on the database structure, and validating queries against the schema. The class also corrects common SQL issues like invalid column references, incompatible joins, and missing table aliases. Additionally, it enhances SQL queries by ensuring proper handling of aggregates, joins, and column mappings, making it a useful tool for generating and optimizing SQL queries in a structured and accurate manner.

**nm4_schema**

The file nm4_schema.py defines a SchemaService class that handles database schema management for SQL queries. The class can read schema definitions from an SQL file or a schema profile. It provides methods for parsing SQL schema definitions, building an index of table and column names, and caching the schema for repeated use. The SchemaService supports loading schema information from SQL files, building a schema index to track tables and columns, and generating a structured representation of the schema. This helps in validating and ensuring the correctness of SQL queries by checking references to tables and columns, ensuring they match the provided schema.

**nm4_data**

The file nm4_data.py provides utilities for executing SQL queries, handling database errors, and normalizing data for display. It includes functions such as _is_transient_db_error, which detects transient database errors like connection failures or timeouts, and run_query, which executes SQL queries using SQLAlchemy, with retry logic in case of certain errors, returning the result as a Pandas DataFrame. Additionally, the file includes normalize_dataframe_for_display, which cleans up column names and normalizes data, converting types like Decimal to float and serializing complex types into JSON strings. Helper functions like _dedupe_columns ensure column name uniqueness, and _normalize_cell_value ensures consistent handling of various data types. Overall, this file is designed to improve data retrieval, error handling, and presentation in a database-driven application.

**nm4_chart**

The file nm4_chart.py provides a set of functions to generate and customize various types of charts based on user input and provided data. It includes the generate_chart function, which analyzes the user's question and data, selects the appropriate chart type (such as bar, pie, line, scatter, or histogram), and constructs the chart accordingly. The file utilizes Plotly Express for chart creation and includes logic to handle different chart types based on data structures and the intent of the question. The _get_chart_spec function generates a specification for the chart, while _build_chart_from_spec creates the chart based on the specified parameters. Additionally, it includes functions to summarize the data, handle numeric series, and even apply rule-based logic for generating year-based charts. This file enables dynamic and flexible data visualization tailored to specific user queries.

**nm4_answer**

The file nm4_answer.py contains a function named generate_answer, which is designed to provide detailed and insightful responses to user queries based on data from a DataFrame. The function analyzes the question and the context of previous conversation history (if available) to generate a tailored answer. It ensures that the response is clear, professional, and formatted according to specific guidelines, such as presenting data in an organized manner and highlighting key insights. The response is structured to include a direct answer, followed by context or interpretation of the data, with formatting tips for clarity. The function uses the call_openai_with_retry to interact with an AI model, which helps generate the final answer. This file is useful for automating the generation of data-driven answers with a professional tone and context.

**Test_cash_invoices_fix**

The file test_cash_invoices_fix.py is a test script designed to verify the correctness of SQL query generation related to payment handling, specifically focusing on preventing cross-table column mistakes. The script simulates a "cash invoices" query, initially using an incorrect SQL query that references the Received column from the Sales table (which does not exist there). The test ensures that a validation function (_validate_column_table_pairs) correctly identifies this error. The script then tests a corrected SQL query that properly references the Received column from the SalePayments table. If the validation succeeds, the script reports a success message, confirming that the fixes work as expected. If issues remain, it prints a failure message. The script is designed to validate and demonstrate the importance of using correct table-column references in SQL queries.

**test_nm4_sql_guardrails**

The file test_nm4_sql_guardrails.py is a test script designed to validate SQL query corrections and ensure compliance with business rules. It uses the SQLService class to apply fixes to queries and check for issues such as improper column references, incorrect join keys, and aggregation errors. The script includes tests that verify alias handling for payment amounts, ensures that DueAmount is not mistakenly pulled from the wrong table, and checks that sum calculations for revenue are wrapped with the COALESCE function to handle null values. It also ensures that joins between SaleItems and Products are correctly rewritten and that incompatible join key types trigger validation errors. If all tests pass successfully, the script prints a confirmation message, ensuring the correctness and reliability of SQL query generation.

**new_main_4**

The file new_main_4.py contains a script that integrates multiple services to process and answer user queries about a database. It begins by loading environment variables such as OPENAI_API_KEY and DATABASE_URL from a .env file. The script sets up connections to OpenAI's API and a database engine using SQLAlchemy. The main components of the script include shared services for schema retrieval, SQL query generation, data querying, and generating answers or charts based on the query results. The core functions include generating SQL from a user's question, running the query on the database, and providing a final answer or a visual representation of the data (such as a chart). The script is designed to handle end-to-end user queries, from retrieving schema and running SQL to generating insightful responses or visualizations based on the data.

**App_4**

The file App_4.py is a Streamlit application designed to provide an interactive database question-and-answer interface. It allows users to ask questions about the database, which are processed by the backend services integrated from new_main_4.py. The app displays the generated SQL query, query results in a data table, and any charts or visualizations that are created in response to the user query. The sidebar offers controls to clear the chat history and view the number of messages exchanged. The app uses OpenAI's API to generate SQL queries and answers based on the schema and the user's question, showing the relevant results and insights in a clean, user-friendly interface. The application handles errors gracefully and provides feedback to users if any issues arise during the process.

**Docker_Files**

The existing files (Dockerfile, .dockerignore, and docker-compose.yml) are used to containerize the application, ensuring that it can run consistently across different environments. The Dockerfile defines the environment for the application, including installing dependencies and setting up the necessary configurations. The .dockerignore file specifies which files and directories should be excluded from the Docker build context, optimizing the build process. The docker-compose.yml file orchestrates the services needed for the application, such as the application itself and any required databases or other services, allowing for easy deployment and management of the application in a containerized environment.



