"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { updateMyDisplayName } from "@/lib/auth";

/** Shown only when the account has no stored full name (legacy signups). */
export function AccountSetNameForm() {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      await updateMyDisplayName(trimmed);
      toast.success("Display name saved");
      setName("");
    } catch (e: unknown) {
      let msg = e instanceof Error ? e.message : "Could not save name";
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) {
        msg =
          "Name save is not available on this API yet. Deploy the latest backend to Render, then try again.";
      }
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1.5 px-1">
      <p className="text-[10px] text-muted-foreground">Add your display name</p>
      <div className="flex gap-1">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
          className="h-8 flex-1 text-xs"
          maxLength={160}
          disabled={busy}
        />
        <Button
          type="button"
          size="sm"
          className="h-8 shrink-0 px-2.5 text-xs"
          disabled={busy || !name.trim()}
          onClick={() => void save()}
        >
          Save
        </Button>
      </div>
    </div>
  );
}
