export function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * Abre uma janela nova, escreve o HTML e dispara a impressão (usada pra gerar
 * PDF via "Salvar como PDF" do diálogo de impressão do navegador). Retorna
 * false quando o navegador bloqueia o popup, pra quem chamar poder avisar o
 * usuário em vez de falhar em silêncio.
 */
export function printHtmlDocument(html: string): boolean {
  const printWindow = window.open("", "_blank", "width=1000,height=700");
  if (!printWindow) return false;
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
  return true;
}
