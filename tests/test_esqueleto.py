def test_pacotes_importaveis():
    import coleta
    import curadoria
    import nucleo

    assert all([coleta, curadoria, nucleo])
