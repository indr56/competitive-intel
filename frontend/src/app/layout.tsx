import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Competitive Moves Intelligence",
  description: "Track competitor website changes and generate AI insights.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
