import "./globals.css";
import type { ReactNode } from "react";

import { ToastProvider } from "@/components/ui/toast";

export const metadata = {
  title: "IT Manager",
  description: "Plataforma web corporativa para gestão de ativos",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
