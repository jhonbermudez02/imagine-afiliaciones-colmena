--
-- PostgreSQL database dump
--

\restrict y2er53gwcGoZ2vaopUF5XtUEzSKgHactXyIAvW7M0fI9ULSsFpxw9eSIbGSCwEh

-- Dumped from database version 15.17
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: lc; Type: TABLE; Schema: public; Owner: escobar
--

CREATE TABLE public.lc (
    fileid text,
    status text,
    userid text,
    nomdoc text,
    cab text,
    fl text,
    ni text,
    pn text
);


ALTER TABLE public.lc OWNER TO escobar;

--
-- PostgreSQL database dump complete
--

\unrestrict y2er53gwcGoZ2vaopUF5XtUEzSKgHactXyIAvW7M0fI9ULSsFpxw9eSIbGSCwEh

