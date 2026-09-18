-- Fila de muestra de dbo.TabCon (contrato 20011357 / ConCon 485701), tomada del
-- servidor real para tener con que trabajar en local.
--
-- AMBITO: solo el SQL Server LOCAL (contenedor imagine_sqlserver). Ver la cabecera de
-- 10-epsdb-tabcon.sql.
--
-- Idempotente: si ya existe ese ConCon no hace nada, para poder re-ejecutarlo sin duplicar.

USE EPSDB;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.TabCon WHERE ConCon = 485701)
INSERT INTO dbo.TabCon (
    [ConCon],
    [ConNumCon],
    [TidCod],
    [ConNumIde],
    [ConDigVer],
    [ConNom],
    [ConNomAbr],
    [AfiTipPerCod],
    [ConDir],
    [ConTel],
    [ConFax],
    [CiuCod],
    [HldCod],
    [ActCod],
    [ConRepLeg],
    [ConCarRepLeg],
    [TipEmpCod],
    [AfiClaEspEmpCod],
    [AfiTipApoCod],
    [AfiTipNomCod],
    [ConNumCO],
    [ConFecCO],
    [ConNumRad],
    [ConFecRad],
    [ConNumGui],
    [ConFecGui],
    [ConIniVig],
    [ConFinVig],
    [AfiClaAfiCod],
    [ConNumConAnt],
    [ConFecDil],
    [ConActNovRec],
    [AfiSucCod],
    [CiuCodAfi],
    [TipProCod],
    [AfiArpCodAnt],
    [AfiLiqApoCod],
    [AfiConEstCod],
    [AfiCauCod],
    [AfiTipNegCod],
    [AfiForPagCod],
    [NumIniCenTra],
    [NumIniCenInd],
    [ConNumIniTra],
    [ConNumIniInd],
    [ConVlrIniSal],
    [ConVlrIniInd],
    [ConEmiIni],
    [ConEmiIniInd],
    [ConFecIng],
    [ConUsuIng],
    [ConFecVal],
    [ConUsuVal],
    [ConFecExp],
    [ConUsuExp],
    [TipLiqIncCod],
    [ConFecCal],
    [ConGenCrn],
    [ConAbvCrn],
    [ConPerMor1],
    [ConPerMor2],
    [ConPerMor3],
    [ConPerMor4],
    [ConIniVigIni],
    [ConValDifTas],
    [AfiTipCieCod],
    [SemActNegCon],
    [ComSemActCod],
    [NichoCod],
    [ConPerGra],
    [ConLiqComPagInd],
    [ConSemPagCom],
    [ConTelCel],
    [ConCorEle],
    [TipApoPILACod],
    [ConSinVinCom],
    [ConCarTraInd],
    [ComMesVen],
    [ConPagIncIndEmp],
    [ConFecCieVen],
    [ConMulSIARL],
    [ConMorIne],
    [IngPan],
    [ConExcSIARL],
    [ConNumIdeCon],
    [SusJur],
    [SusJurDet],
    [ConTipAfiCod],
    [ConZon],
    [ConLocCom],
    [ConAut046],
    [ConAut047],
    [ConAut048],
    [ConAfiCre],
    [NumIniSed],
    [ConRepLegIde],
    [ConAut049],
    [ConAut050],
    [ConAut051],
    [ConIngSAT],
    [RieNivRieCod],
    [RiePEPCod],
    [RieResCod],
    [RieFecAct],
    [RieUsuAct],
    [ConExcFac],
    [ConNomLar],
    [ConPerPubExp],
    [AfiCanVenCod],
    [CodCamVen],
    [ClaApoPILACod],
    [ResPagMorCod],
    [ConObsTex]
)
VALUES (
    485701,                           -- [ConCon]
    '20011357',                       -- [ConNumCon]
    'NI',                             -- [TidCod]
    '902081769',                      -- [ConNumIde]
    3,                                -- [ConDigVer]
    'UNION TEMPORAL SC ARC SAE 2026', -- [ConNom]
    'UNION TEMPORAL SC ARC SAE 2026', -- [ConNomAbr]
    'J',                              -- [AfiTipPerCod]
    'CRA 16#93-11',                   -- [ConDir]
    '3103128267',                     -- [ConTel]
    '0000000',                        -- [ConFax]
    '11001',                          -- [CiuCod]
    '00000',                          -- [HldCod]
    '1620901',                        -- [ActCod]
    'LUIS GUILLERMO NAVAS',           -- [ConRepLeg]
    'REPRESENTANTE LEGAL',            -- [ConCarRepLeg]
    '2',                              -- [TipEmpCod]
    '02',                             -- [AfiClaEspEmpCod]
    'P',                              -- [AfiTipApoCod]
    'C',                              -- [AfiTipNomCod]
    240826,                           -- [ConNumCO]
    '2026-08-24T00:00:00.000',        -- [ConFecCO]
    '16001',                          -- [ConNumRad]
    '2026-08-24T00:00:00.000',        -- [ConFecRad]
    '658811',                         -- [ConNumGui]
    '2026-08-25T00:00:00.000',        -- [ConFecGui]
    '2026-08-25T00:00:00.000',        -- [ConIniVig]
    '2050-12-31T00:00:00.000',        -- [ConFinVig]
    '2',                              -- [AfiClaAfiCod]
    '',                               -- [ConNumConAnt]
    '2026-08-24T00:00:00.000',        -- [ConFecDil]
    'N',                              -- [ConActNovRec]
    '16',                             -- [AfiSucCod]
    '11001',                          -- [CiuCodAfi]
    '3',                              -- [TipProCod]
    '00000',                          -- [AfiArpCodAnt]
    1,                                -- [AfiLiqApoCod]
    '3',                              -- [AfiConEstCod]
    '00',                             -- [AfiCauCod]
    '9',                              -- [AfiTipNegCod]
    '1',                              -- [AfiForPagCod]
    1,                                -- [NumIniCenTra]
    1,                                -- [NumIniCenInd]
    4,                                -- [ConNumIniTra]
    0,                                -- [ConNumIniInd]
    9400000.0000,                     -- [ConVlrIniSal]
    0.0000,                           -- [ConVlrIniInd]
    49068.0000,                       -- [ConEmiIni]
    0.0000,                           -- [ConEmiIniInd]
    '2026-08-25T14:00:59.403',        -- [ConFecIng]
    'J2P7H2A5',                       -- [ConUsuIng]
    '2026-08-25T14:22:40.557',        -- [ConFecVal]
    'J2P7H2A5',                       -- [ConUsuVal]
    '2026-08-25T14:22:41.010',        -- [ConFecExp]
    'J2P7H2A5',                       -- [ConUsuExp]
    '00',                             -- [TipLiqIncCod]
    '2026-09-01T00:00:00.000',        -- [ConFecCal]
    'S',                              -- [ConGenCrn]
    'S',                              -- [ConAbvCrn]
    '1900-01-01T00:00:00.000',        -- [ConPerMor1]
    '1900-01-01T00:00:00.000',        -- [ConPerMor2]
    '1900-01-01T00:00:00.000',        -- [ConPerMor3]
    '1900-01-01T00:00:00.000',        -- [ConPerMor4]
    '2026-08-25T00:00:00.000',        -- [ConIniVigIni]
    0,                                -- [ConValDifTas]
    '00000',                          -- [AfiTipCieCod]
    0,                                -- [SemActNegCon]
    '1',                              -- [ComSemActCod]
    '016',                            -- [NichoCod]
    0,                                -- [ConPerGra]
    0,                                -- [ConLiqComPagInd]
    0,                                -- [ConSemPagCom]
    '3103128267',                     -- [ConTelCel]
    'TALENTO.HUMANO@CONVIEST.COM',    -- [ConCorEle]
    '4',                              -- [TipApoPILACod]
    0,                                -- [ConSinVinCom]
    0,                                -- [ConCarTraInd]
    '1900-01-01T00:00:00.000',        -- [ComMesVen]
    0,                                -- [ConPagIncIndEmp]
    '1900-01-01T00:00:00.000',        -- [ConFecCieVen]
    0,                                -- [ConMulSIARL]
    0,                                -- [ConMorIne]
    0,                                -- [IngPan]
    0,                                -- [ConExcSIARL]
    '',                               -- [ConNumIdeCon]
    0,                                -- [SusJur]
    '',                               -- [SusJurDet]
    'A',                              -- [ConTipAfiCod]
    'U',                              -- [ConZon]
    'chapinero',                      -- [ConLocCom]
    0,                                -- [ConAut046]
    0,                                -- [ConAut047]
    0,                                -- [ConAut048]
    0,                                -- [ConAfiCre]
    1,                                -- [NumIniSed]
    3576406,                          -- [ConRepLegIde]
    1,                                -- [ConAut049]
    1,                                -- [ConAut050]
    1,                                -- [ConAut051]
    0,                                -- [ConIngSAT]
    '00000',                          -- [RieNivRieCod]
    '00000',                          -- [RiePEPCod]
    '00000',                          -- [RieResCod]
    '1900-01-01T00:00:00.000',        -- [RieFecAct]
    '',                               -- [RieUsuAct]
    0,                                -- [ConExcFac]
    'UNION TEMPORAL SC ARC SAE 2026', -- [ConNomLar]
    0,                                -- [ConPerPubExp]
    '1',                              -- [AfiCanVenCod]
    '202409',                         -- [CodCamVen]
    'C',                              -- [ClaApoPILACod]
    '0',                              -- [ResPagMorCod]
    ''                                -- [ConObsTex]
);
GO
