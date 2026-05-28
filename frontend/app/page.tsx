"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart2,
  Building2,
  CheckCircle2,
  Coins,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MetaMaskIcon } from "@/components/icons/metamask";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { signIn, registerWallet } from "@/lib/auth";
import { getSession } from "@/lib/api";
import { toast } from "sonner";
import { cn, shortAddress } from "@/lib/utils";

type Role = "investor" | "property_owner" | "tenant";

const ROLE_OPTIONS: { id: Role; title: string; description: string }[] = [
  { id: "investor", title: "Investor", description: "Buy fractional property tokens and earn rental yield." },
  { id: "tenant", title: "Tenant", description: "Rent a property and pay monthly rent on-chain." },
  { id: "property_owner", title: "Property Owner", description: "List and manage real estate properties." },
];

const FEATURE_GRID = [
  { icon: Building2, label: "Property tokenization" },
  { icon: Coins, label: "Automatic rent distribution" },
  { icon: ShieldCheck, label: "Wallet-based authentication" },
  { icon: BarChart2, label: "Live portfolio analytics" },
] as const;

export default function LandingPage() {
  const router = useRouter();
  const [view, setView] = useState<"connect" | "register" | "redirect">("connect");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingWallet, setPendingWallet] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [email, setEmail] = useState("");

  useEffect(() => {
    const session = getSession();
    if (session?.user?.role) {
      router.replace(`/${session.user.role}`);
    }
  }, [router]);

  async function handleConnect() {
    setError(null);
    setBusy(true);
    try {
      const result = await signIn();
      if (result.status === "authenticated") {
        toast.success("Signed in.");
        setView("redirect");
        router.push(`/${result.session.user.role}`);
      } else {
        setPendingWallet(result.walletAddress);
        setRole(null);
        setView("register");
      }
    } catch (e: any) {
      const msg = e?.message || "Sign-in failed.";
      const isReject = /denied|rejected/i.test(msg);
      setError(isReject ? "Signature canceled in MetaMask." : msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleRegister() {
    if (!pendingWallet || !role) return;
    setError(null);
    setBusy(true);
    try {
      const session = await registerWallet({
        walletAddress: pendingWallet,
        role,
        email: email.trim() || null,
      });
      toast.success("Account created.");
      setView("redirect");
      router.push(`/${session.user.role}`);
    } catch (e: any) {
      setError(e?.message || "Registration failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.18),transparent_34%),radial-gradient(circle_at_85%_20%,hsl(var(--chart-2)/0.16),transparent_30%),linear-gradient(to_bottom,hsl(var(--background)),hsl(var(--background)))]" />
      <div className="pointer-events-none absolute inset-0 -z-10 bg-grid opacity-25 [mask-image:linear-gradient(to_bottom,white,transparent_72%)]" />

      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5 md:px-8">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-primary via-chart-3 to-chart-2 font-bold text-primary-foreground shadow-lg shadow-primary/20">
            E
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold md:text-base">EstateChain</span>
            <span className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">Real Estate Web3</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://sepolia.etherscan.io"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-full border border-border/70 bg-card/70 px-3 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur transition hover:border-primary/30 hover:text-foreground sm:inline"
          >
            Sepolia explorer
          </a>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-10 px-6 pb-16 pt-12 lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.9fr)] lg:items-start lg:px-8 lg:pb-24 lg:pt-16">
        <motion.section
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex flex-col"
        >
          <span className="inline-flex w-fit items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_18px_hsl(var(--primary))]" />
            Live on Ethereum Sepolia
          </span>
          <h1 className="mt-6 max-w-xl text-balance text-5xl font-semibold leading-[0.98] tracking-tight md:text-6xl">
            Tokenized real estate,
            <span className="block bg-gradient-to-r from-primary via-chart-3 to-chart-2 bg-clip-text text-transparent">
              on-chain rent.
            </span>
          </h1>
          <p className="mt-5 max-w-xl text-balance text-base leading-7 text-muted-foreground">
            EstateChain turns properties into fractional ERC-20 tokens, and pays rent directly to investors through a single rent contract. No intermediaries, no spreadsheets — just on-chain ownership.
          </p>

          <div className="mt-7 grid max-w-xl gap-2.5 sm:grid-cols-2">
            {FEATURE_GRID.map((feature) => (
              <div key={feature.label} className="rounded-xl border border-border/70 bg-card/60 px-3 py-2.5 shadow-sm backdrop-blur">
                <div className="flex items-center gap-2.5">
                  <feature.icon className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium">{feature.label}</span>
                </div>
              </div>
            ))}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.05 }}
          className="relative overflow-hidden rounded-2xl border border-border/70 bg-card/80 p-6 shadow-2xl shadow-primary/5 backdrop-blur"
        >
          {view === "connect" && (
            <div className="relative flex flex-col gap-4">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight">Sign in with your wallet</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  We use a MetaMask signature as your identity. No passwords, no gas.
                </p>
              </div>
              <Button onClick={handleConnect} disabled={busy} size="lg" className="h-12 gap-2 rounded-2xl">
                <MetaMaskIcon size={18} />
                {busy ? "Awaiting signature…" : "Connect with MetaMask"}
              </Button>
              {error && (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {error}
                </p>
              )}
              <ul className="space-y-1.5 text-xs leading-5 text-muted-foreground">
                <li>* You'll sign a one-time message. Nothing is broadcast on-chain.</li>
                <li>* Your wallet is your identity. Roles are bound at sign-up.</li>
                <li>* Network: Sepolia (chainId 11155111).</li>
              </ul>
            </div>
          )}

          {view === "register" && (
            <div className="relative flex flex-col gap-5">
              <div>
                <span className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.18em] text-primary">
                  <Sparkles className="h-3.5 w-3.5" />
                  Account setup
                </span>
                <h2 className="mt-4 text-2xl font-semibold tracking-tight">Choose your workspace</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Pick how you'll use the platform. This choice is bound to your wallet.
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/50 px-4 py-3 font-mono text-xs">
                {shortAddress(pendingWallet, 8, 6)}
              </div>
              <div className="flex flex-col gap-2">
                {ROLE_OPTIONS.map((opt) => {
                  const active = role === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setRole(opt.id)}
                      className={cn(
                        "flex flex-col gap-1 rounded-2xl border px-4 py-3 text-left transition-all",
                        active
                          ? "border-primary bg-primary/10 shadow-lg shadow-primary/10"
                          : "border-border/70 bg-background/40 hover:border-primary/30 hover:bg-muted/60",
                      )}
                    >
                      <span className="text-sm font-medium">{opt.title}</span>
                      <span className="text-xs text-muted-foreground">{opt.description}</span>
                    </button>
                  );
                })}
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="email">Email (optional)</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="h-11 rounded-2xl"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Button onClick={handleRegister} disabled={busy || !role} size="lg" className="h-12 rounded-2xl">
                  {busy ? "Signing…" : "Create Account"}
                  {!busy && <ArrowRight className="h-4 w-4" />}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setPendingWallet(null);
                    setRole(null);
                    setError(null);
                    setView("connect");
                  }}
                >
                  Use a different wallet
                </Button>
              </div>
              {error && (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {error}
                </p>
              )}
            </div>
          )}

          {view === "redirect" && (
            <div className="relative flex flex-col items-start gap-2">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-success/15 text-success">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="mt-2 text-xl font-semibold tracking-tight">Signed in</h2>
              <p className="text-sm text-muted-foreground">Redirecting to your dashboard…</p>
            </div>
          )}
        </motion.section>
      </main>

      <footer className="border-t border-border/60 px-6 py-5 text-xs text-muted-foreground md:px-8">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-2 md:flex-row md:items-center">
          <span>© {new Date().getFullYear()} EstateChain — Tokenized real estate on Sepolia.</span>
          <span className="font-mono">chainId 0xaa36a7</span>
        </div>
      </footer>
    </div>
  );
}
