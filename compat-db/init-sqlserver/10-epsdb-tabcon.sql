-- TabCon (base EPSDB, SQL Server).
--
-- AMBITO: solo el SQL Server LOCAL de pruebas (contenedor imagine_sqlserver). El servidor
-- real ya tiene esta tabla con sus datos; este script existe para que un contenedor limpio
-- quede igual al entorno de trabajo local. NO se ejecuta contra el servidor.
--
-- Estructura tomada de la definicion del servidor real (113 columnas). Se respetan tipos,
-- longitudes y nulabilidad tal cual: el unico campo que admite NULL es ConNumIdeCon.
--
-- SIN PRIMARY KEY ni indices a proposito: la definicion recibida no trae informacion de
-- restricciones, y en este proyecto ya paso que una PK inventada sobre un catalogo
-- (img004.epsriesgos) descartara filas en silencio. Si el servidor real tiene PK sobre
-- ConCon o ConNumCon, se agrega cuando se confirme.
--
-- A diferencia de Postgres, la imagen de SQL Server NO ejecuta scripts de arranque sola.
-- Se aplica a mano:
--   docker exec -i imagine_sqlserver /opt/mssql-tools18/bin/sqlcmd --     -S localhost -U sa -P "" -C -i /ruta/10-epsdb-tabcon.sql

IF DB_ID('EPSDB') IS NULL
    CREATE DATABASE EPSDB;
GO

USE EPSDB;
GO

IF OBJECT_ID('dbo.TabCon', 'U') IS NOT NULL
    DROP TABLE dbo.TabCon;
GO

CREATE TABLE dbo.TabCon (
    [ConCon]          int            NOT NULL,
    [ConNumCon]       varchar(25)    NOT NULL,
    [TidCod]          varchar(5)     NOT NULL,
    [ConNumIde]       varchar(15)    NOT NULL,
    [ConDigVer]       tinyint        NOT NULL,
    [ConNom]          varchar(100)   NOT NULL,
    [ConNomAbr]       varchar(40)    NOT NULL,
    [AfiTipPerCod]    char(1)        NOT NULL,
    [ConDir]          varchar(100)   NOT NULL,
    [ConTel]          varchar(60)    NOT NULL,
    [ConFax]          varchar(60)    NOT NULL,
    [CiuCod]          varchar(5)     NOT NULL,
    [HldCod]          varchar(5)     NOT NULL,
    [ActCod]          varchar(7)     NOT NULL,
    [ConRepLeg]       varchar(40)    NOT NULL,
    [ConCarRepLeg]    varchar(40)    NOT NULL,
    [TipEmpCod]       varchar(2)     NOT NULL,
    [AfiClaEspEmpCod] varchar(2)     NOT NULL,
    [AfiTipApoCod]    char(1)        NOT NULL,
    [AfiTipNomCod]    char(1)        NOT NULL,
    [ConNumCO]        int            NOT NULL,
    [ConFecCO]        datetime       NOT NULL,
    [ConNumRad]       varchar(10)    NOT NULL,
    [ConFecRad]       datetime       NOT NULL,
    [ConNumGui]       varchar(12)    NOT NULL,
    [ConFecGui]       datetime       NOT NULL,
    [ConIniVig]       datetime       NOT NULL,
    [ConFinVig]       datetime       NOT NULL,
    [AfiClaAfiCod]    varchar(5)     NOT NULL,
    [ConNumConAnt]    varchar(25)    NOT NULL,
    [ConFecDil]       datetime       NOT NULL,
    [ConActNovRec]    char(1)        NOT NULL,
    [AfiSucCod]       varchar(5)     NOT NULL,
    [CiuCodAfi]       varchar(5)     NOT NULL,
    [TipProCod]       varchar(2)     NOT NULL,
    [AfiArpCodAnt]    varchar(5)     NOT NULL,
    [AfiLiqApoCod]    int            NOT NULL,
    [AfiConEstCod]    varchar(5)     NOT NULL,
    [AfiCauCod]       varchar(5)     NOT NULL,
    [AfiTipNegCod]    varchar(3)     NOT NULL,
    [AfiForPagCod]    varchar(5)     NOT NULL,
    [NumIniCenTra]    int            NOT NULL,
    [NumIniCenInd]    int            NOT NULL,
    [ConNumIniTra]    int            NOT NULL,
    [ConNumIniInd]    int            NOT NULL,
    [ConVlrIniSal]    money          NOT NULL,
    [ConVlrIniInd]    money          NOT NULL,
    [ConEmiIni]       money          NOT NULL,
    [ConEmiIniInd]    money          NOT NULL,
    [ConFecIng]       datetime       NOT NULL,
    [ConUsuIng]       varchar(8)     NOT NULL,
    [ConFecVal]       datetime       NOT NULL,
    [ConUsuVal]       varchar(8)     NOT NULL,
    [ConFecExp]       datetime       NOT NULL,
    [ConUsuExp]       varchar(8)     NOT NULL,
    [TipLiqIncCod]    varchar(2)     NOT NULL,
    [ConFecCal]       datetime       NOT NULL,
    [ConGenCrn]       char(1)        NOT NULL,
    [ConAbvCrn]       char(1)        NOT NULL,
    [ConPerMor1]      datetime       NOT NULL,
    [ConPerMor2]      datetime       NOT NULL,
    [ConPerMor3]      datetime       NOT NULL,
    [ConPerMor4]      datetime       NOT NULL,
    [ConIniVigIni]    datetime       NOT NULL,
    [ConValDifTas]    bit            NOT NULL,
    [AfiTipCieCod]    varchar(5)     NOT NULL,
    [SemActNegCon]    int            NOT NULL,
    [ComSemActCod]    varchar(5)     NOT NULL,
    [NichoCod]        varchar(5)     NOT NULL,
    [ConPerGra]       bit            NOT NULL,
    [ConLiqComPagInd] bit            NOT NULL,
    [ConSemPagCom]    bit            NOT NULL,
    [ConTelCel]       varchar(60)    NOT NULL,
    [ConCorEle]       varchar(125)   NOT NULL,
    [TipApoPILACod]   varchar(5)     NOT NULL,
    [ConSinVinCom]    bit            NOT NULL,
    [ConCarTraInd]    bit            NOT NULL,
    [ComMesVen]       datetime       NOT NULL,
    [ConPagIncIndEmp] bit            NOT NULL,
    [ConFecCieVen]    datetime       NOT NULL,
    [ConMulSIARL]     bit            NOT NULL,
    [ConMorIne]       bit            NOT NULL,
    [IngPan]          bit            NOT NULL,
    [ConExcSIARL]     bit            NOT NULL,
    [ConNumIdeCon]    varchar(4)     NULL,
    [SusJur]          bit            NOT NULL,
    [SusJurDet]       varchar(200)   NOT NULL,
    [ConTipAfiCod]    varchar(5)     NOT NULL,
    [ConZon]          char(1)        NOT NULL,
    [ConLocCom]       varchar(100)   NOT NULL,
    [ConAut046]       bit            NOT NULL,
    [ConAut047]       bit            NOT NULL,
    [ConAut048]       bit            NOT NULL,
    [ConAfiCre]       bit            NOT NULL,
    [NumIniSed]       int            NOT NULL,
    [ConRepLegIde]    int            NOT NULL,
    [ConAut049]       bit            NOT NULL,
    [ConAut050]       bit            NOT NULL,
    [ConAut051]       bit            NOT NULL,
    [ConIngSAT]       bit            NOT NULL,
    [RieNivRieCod]    varchar(5)     NOT NULL,
    [RiePEPCod]       varchar(5)     NOT NULL,
    [RieResCod]       varchar(5)     NOT NULL,
    [RieFecAct]       datetime       NOT NULL,
    [RieUsuAct]       varchar(8)     NOT NULL,
    [ConExcFac]       bit            NOT NULL,
    [ConNomLar]       varchar(250)   NOT NULL,
    [ConPerPubExp]    bit            NOT NULL,
    [AfiCanVenCod]    varchar(4)     NOT NULL,
    [CodCamVen]       varchar(8)     NOT NULL,
    [ClaApoPILACod]   varchar(5)     NOT NULL,
    [ResPagMorCod]    char(1)        NOT NULL,
    [ConObsTex]       varchar(125)   NOT NULL
);
GO
