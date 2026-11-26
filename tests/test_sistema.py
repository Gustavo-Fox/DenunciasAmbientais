"""Testes automáticos do sistema. Rodar na pasta do projeto:  python -m unittest discover -t . -s tests -v"""
import datetime
import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
from sistema import create_app, config as cfg

try:
    from PIL import Image
except ImportError:
    Image = None

ANO = datetime.date.today().year


def form(**kw):
    """Campos mínimos do formulário de cadastro; kw sobrescreve."""
    d = dict(criada=f"{ANO}-11-20", categoria_id="1", prioridade="Normal", descricao="Teste", logradouro="Rua A", numero="1",
             bairro="B", municipio="M", referencia="", lat="-29,5", lon="-55,1", resp_nome="", resp_cpf="", resp_contato="",
             reincidente="0", legislacao="", denunciante="", contato="")
    d.update(kw)
    return d


def imagem(formato="JPEG", tam=(800, 600)):
    b = io.BytesIO()
    Image.new("RGB", tam, "green").save(b, formato)
    return b.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name)
        self.c = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def sql(self, sql, a=()):
        cx = sqlite3.connect(self.app.config["DB"])
        try:
            return cx.execute(sql, a).fetchall()
        finally:
            cx.close()

    def grava(self, sql, a=()):
        cx = sqlite3.connect(self.app.config["DB"])
        cx.execute(sql, a)
        cx.commit()
        cx.close()

    def novo(self, **kw):
        self.c.post("/nova", data=form(**kw), content_type="multipart/form-data")
        return self.sql("select max(id) from denuncias")[0][0]


class Chamados(Base):
    def test_codigos_com_sequencias_separadas(self):
        self.novo(); self.novo(tipo="fiscalizacao", fiscal="Ana"); self.novo(tipo="fiscalizacao")
        self.assertEqual([r[0] for r in self.sql("select codigo from denuncias order by id")],
                         [f"DEN-{ANO}-00001", f"FIS-{ANO}-00001", f"FIS-{ANO}-00002"])

    def test_dados_invalidos_e_chamado_inexistente(self):
        self.assertEqual(self.c.post("/nova", data=form(lat="295")).status_code, 400)
        self.assertEqual(self.c.post("/nova", data=form(criada="31/12/2026")).status_code, 400)
        self.assertEqual(self.c.post("/d/999/revisita", data={"prevista": "2026-12-01"}).status_code, 404)

    def test_edicao_registra_correcao(self):
        n = self.novo()
        self.c.post(f"/d/{n}/editar", data=form(numero="99", autor="Ana"))
        self.assertIn("Cadastro corrigido: Número.", self.c.get(f"/d/{n}").get_data(as_text=True))

    def test_texto_digitado_e_escapado(self):
        n = self.novo(descricao='<script>alert(1)</script>')
        self.assertNotIn("<script>alert(1)", self.c.get(f"/d/{n}").get_data(as_text=True))

    def test_envio_de_outro_site_e_bloqueado(self):
        self.assertEqual(self.c.post("/nova", data=form(), headers={"Origin": "http://outro.com"}).status_code, 403)

    def test_revisita_concluida_duas_vezes_gera_um_registro(self):
        n = self.novo()
        self.c.post(f"/d/{n}/revisita", data={"prevista": f"{ANO}-12-01"})
        for _ in range(2):
            self.c.post("/revisita/1/feita", data={"obs": "Visto", "fiscal": "Ana"})
        self.assertEqual(self.sql("select count(*) from acompanhamentos where tipo='Revisita'")[0][0], 1)

    def test_paginacao(self):
        for _ in range(3):
            self.novo()
        cx = sqlite3.connect(self.app.config["DB"])
        cx.execute("insert into enderecos(logradouro) values('R')")
        for i in range(60):
            cx.execute("insert into denuncias(codigo,criada,endereco_id,descricao) values(?,?,1,'x')", (f"TST-{i:05d}", "2026-01-01"))
        cx.commit(); cx.close()
        self.assertIn("Página 2 de 2", self.c.get("/?page=2").get_data(as_text=True))


class Cancelamento(Base):
    def test_cancelar_exige_justificativa_e_nao_apaga(self):
        n = self.novo()
        self.c.post(f"/d/{n}/cancelar", data={"motivo": "curto"})
        self.assertEqual(self.sql("select status from denuncias")[0][0], "Recebida")
        self.c.post(f"/d/{n}/cancelar", data={"motivo": "Denúncia duplicada do chamado anterior", "autor": "Ana"})
        self.assertEqual(self.sql("select status, status_anterior from denuncias")[0], ("Cancelada", "Recebida"))
        h = self.c.get(f"/d/{n}").get_data(as_text=True)
        self.assertIn("Chamado cancelado", h); self.assertIn("duplicada", h)

    def test_chamado_cancelado_nao_aceita_alteracoes_e_pode_ser_reativado(self):
        n = self.novo()
        self.c.post(f"/d/{n}/acompanhar", data=dict(data=f"{ANO}-11-21", tipo="Vistoria", status="Notificada", texto="ok"))
        self.c.post(f"/d/{n}/cancelar", data={"motivo": "Registrado por engano no sistema"})
        self.c.post(f"/d/{n}/acompanhar", data=dict(data=f"{ANO}-11-22", tipo="Vistoria", texto="não deve entrar"))
        self.assertEqual(self.sql("select count(*) from acompanhamentos where texto='não deve entrar'")[0][0], 0)
        self.assertEqual(self.c.get(f"/d/{n}/editar").status_code, 302)
        self.c.post(f"/d/{n}/reativar", data={"motivo": "Cancelado por engano, chamado válido"})
        self.assertEqual(self.sql("select status from denuncias")[0][0], "Notificada")
        self.assertEqual(self.c.get("/?status=Cancelada").status_code, 200)

    def test_cancelado_sai_do_andamento_e_das_revisitas(self):
        n = self.novo()
        self.c.post(f"/d/{n}/revisita", data={"prevista": "2020-01-01"})
        self.c.post(f"/d/{n}/cancelar", data={"motivo": "Registrado por engano no sistema"})
        self.assertIn("Nenhuma revisita pendente", self.c.get("/revisitas").get_data(as_text=True))


class Anexos(Base):
    def enviar(self, n, nome, conteudo, **kw):
        return self.c.post(f"/d/{n}/acompanhar", content_type="multipart/form-data", follow_redirects=True,
                           data=dict(data=f"{ANO}-11-21", tipo="Atualização", texto="com anexo", arquivos=(io.BytesIO(conteudo), nome), **kw))

    def test_tipo_nao_permitido_e_conteudo_falso_sao_recusados(self):
        n = self.novo()
        h = self.enviar(n, "virus.exe", b"MZ" + b"0" * 50).get_data(as_text=True)
        self.assertIn("tipo de arquivo não permitido", h)
        self.assertIn("não corresponde", self.enviar(n, "falso.pdf", b"isto nao e um pdf").get_data(as_text=True))
        self.assertEqual(self.sql("select count(*) from anexos")[0][0], 0)

    def test_limite_por_arquivo(self):
        n = self.novo()
        cfg.LIMITES_MB["documentos"] = 0.0001
        try:
            self.assertIn("maior que", self.enviar(n, "a.pdf", b"%PDF" + b"0" * 500).get_data(as_text=True))
        finally:
            cfg.LIMITES_MB["documentos"] = 25

    def test_pdf_abre_no_navegador_e_anexo_html_antigo_e_baixado(self):
        n = self.novo()
        self.enviar(n, "laudo.pdf", b"%PDF-1.4 teste")
        r = self.c.get("/anexos/1/arquivo")
        self.assertEqual((r.status_code, r.headers["X-Content-Type-Options"]), (200, "nosniff"))
        self.assertNotIn("attachment", r.headers.get("Content-Disposition", ""))
        r.close()
        open(os.path.join(self.app.config["UP"], "x.html"), "w").write("<script>1</script>")
        self.grava("insert into anexos(denuncia_id,nome,arquivo) values(?,?,?)", (n, "x.html", "x.html"))  # anexo de versão antiga
        r = self.c.get("/anexos/2/arquivo")
        self.assertIn("attachment", r.headers.get("Content-Disposition", ""))
        r.close()

    @unittest.skipUnless(Image, "Pillow não instalado")
    def test_miniatura_substituir_e_remover(self):
        n = self.novo()
        self.enviar(n, "foto.jpg", imagem())
        mini = self.c.get("/anexos/1/mini")
        self.assertEqual((mini.status_code, mini.mimetype), (200, "image/jpeg"))
        self.assertLessEqual(Image.open(io.BytesIO(mini.data)).width, 360)
        self.assertIn("foto.jpg", self.c.get(f"/d/{n}").get_data(as_text=True))
        antigo = self.sql("select arquivo from anexos where id=1")[0][0]
        self.c.post("/anexos/1/gerir", content_type="multipart/form-data",
                    data=dict(acao="substituir", motivo="Foto errada", autor="Ana", arquivo=(io.BytesIO(imagem("PNG")), "nova.png")))
        self.assertEqual(self.sql("select removido_em is not null, removido_por from anexos where id=1")[0], (1, "Ana"))
        self.assertTrue(os.path.exists(os.path.join(self.app.config["UP"], "_removidos", antigo)))
        self.assertEqual(self.c.get("/anexos/1/arquivo").status_code, 404)
        self.c.post("/anexos/2/gerir", data=dict(acao="remover", motivo="Imagem duplicada"))
        self.assertEqual(self.sql("select count(*) from anexos where removido_em is null")[0][0], 0)
        h = self.c.get(f"/d/{n}").get_data(as_text=True)
        self.assertIn("Anexo substituído: foto.jpg", h); self.assertIn("Anexo removido: nova.png", h)

    def test_remocao_exige_motivo(self):
        n = self.novo()
        self.enviar(n, "laudo.pdf", b"%PDF-1.4 teste")
        self.c.post("/anexos/1/gerir", data=dict(acao="remover", motivo=""))
        self.assertEqual(self.sql("select removido_em from anexos")[0][0], None)

    @unittest.skipUnless(Image, "Pillow não instalado")
    def test_backup_inclui_anexos_removidos_e_nao_miniaturas(self):
        n = self.novo()
        self.enviar(n, "foto.jpg", imagem()); self.c.get("/anexos/1/mini")
        self.c.post("/anexos/1/gerir", data=dict(acao="remover", motivo="Teste de backup"))
        self.enviar(n, "b.jpg", imagem())
        nomes = zipfile.ZipFile(io.BytesIO(self.c.post("/backup").data)).namelist()
        self.assertIn("denuncias.db", nomes)
        self.assertTrue(any(x.startswith("uploads/_removidos/") for x in nomes))
        self.assertFalse(any("_mini" in x for x in nomes))


class Relatorio(Base):
    def test_registros_do_sistema_nao_contam_como_produtividade(self):
        n = self.novo(tipo="fiscalizacao", fiscal="Ana")
        self.c.post(f"/d/{n}/editar", data=form(numero="5", fiscal="Ana", autor="Ana"))
        self.c.post(f"/d/{n}/cancelar", data={"motivo": "Registrado por engano no sistema"})
        h = self.c.get(f"/relatorio?mes={ANO}-11").get_data(as_text=True)
        self.assertNotIn("Cadastro corrigido", h); self.assertIn("Por fiscal: Ana (1)", h)
        self.assertEqual(self.c.get("/relatorio?mes=abc").status_code, 200)


if __name__ == "__main__":
    unittest.main()
