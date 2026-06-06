import type { Metadata } from "next";

import { Providers } from "@/app/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Bridge OS",
  description:
    "The operating system for Blood Bridges. Software infrastructure to scale Blood Warriors' Blood Bridge model for recurring thalassemia transfusion care across India.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-white antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
