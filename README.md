# Prueba Taller 2

classDiagram
    class Cliente {
        +id: int
        +nombre: str
        +email: str
        +puntos: int
        +nivel: str
        +fecha_registro: str
        +calcular_puntos(monto_cop, tarjeta_aliada) int
        +aplicar_upgrade_si_corresponde() str
        +beneficios() list~str~
        -_multiplicador_tier() float
    }

    class ClienteBronce {
        +_multiplicador_tier() float
        +beneficios() list~str~
    }

    class ClientePlata {
        +_multiplicador_tier() float
        +beneficios() list~str~
    }

    class ClienteOro {
        +_multiplicador_tier() float
        +beneficios() list~str~
    }

    class ClienteRepo {
        +crear(nombre, email)
        +obtener(cliente_id)
        +actualizar(cliente_id, puntos, nivel)
        +obtener_por_email(email)
    }

    class TransaccionRepo {
        +registrar(cliente_id, monto_cop, tarjeta_aliada, puntos_g, puntos_r, desc)
        +historial(cliente_id)
    }

    class RecompensaRepo {
        +listar()
        +obtener(recompensa_id)
    }

    class LoyaltyEngine {
        +registrar_cliente(nombre, email)
        +registrar_compra(cliente_id, monto_cop, tarjeta_aliada, descripcion)
        +redimir(cliente_id, recompensa_id)
        +ver_cliente(cliente_id)
        +listar_recompensas()
        +historial(cliente_id)
    }

    Cliente <|-- ClienteBronce
    Cliente <|-- ClientePlata
    Cliente <|-- ClienteOro
    LoyaltyEngine --> ClienteRepo
    LoyaltyEngine --> TransaccionRepo
    LoyaltyEngine --> RecompensaRepo
