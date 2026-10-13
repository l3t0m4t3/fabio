from caixaeletronico import Banco, Caixa

banco = Banco()
caixas = {
    1: Caixa("Caixa 1", banco),
    2: Caixa("Caixa 2", banco),
    3: Caixa("Caixa 3", banco),
}
logger.info("Sistema iniciado")
while True:
    print("Você está em um banco. Escolha um caixa.")
    escolha = input(
        "CAIXA 1 ---- CAIXA 2 ---- CAIXA 3 (escolha 1, 2 ou 3, ou 0 para encerrar):\n"
    )
    if escolha == "0":
        print("Encerrando. Até logo!")
        logger.info("Sistema encerrado")
        break
    if not escolha.isdigit() or int(escolha) not in caixas:
        print("Caixa inválido, tente novamente.\n")
        continue
    cx = caixas[int(escolha)]
    while True:
        print("Agora escolha a operação")
        operacao = input("1 - sacar\n2 - sair\n")
        if operacao == "2":
            break
        elif operacao == "1":
            entrada = input("Informe o valor a ser sacado:\n")
            if not entrada.isdigit():
                print("Digite apenas números inteiros.")
                continue

            try:
                saque = cx.sacar(int(entrada))
            except ValueError as erro:
                print(f"Não foi possível sacar: {erro}")
                continue
            print("Foi sacado:")

            for nota, qtd in saque.items():
                plural = "s" if qtd > 1 else ""
                print(f"{qtd} cédula{plural} de {nota.name} reais")

        else:
            print("Operação inválida, tente novamente.")