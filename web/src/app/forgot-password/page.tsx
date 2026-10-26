"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { AuthLayout } from "@/components/auth-layout";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { api, ApiError } from "@/lib/api";
import { forgotSchema } from "@/lib/schemas";

type Values = z.infer<typeof forgotSchema>;

export default function ForgotPasswordPage() {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(forgotSchema) });

  async function onSubmit(values: Values) {
    setError(null);
    try {
      const res = await api<{ message: string }>("/api/auth/password/forgot", { method: "POST", body: values });
      setDone(res.message);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Request failed.");
    }
  }

  return (
    <AuthLayout title="Reset your password" subtitle="We'll email you a link that works for 30 minutes." footer={<Link href="/login" className="text-[var(--accent)] hover:underline">Back to sign in</Link>}>
      {done ? (
        <Alert kind="success">{done}</Alert>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {error && <Alert>{error}</Alert>}
          <Field label="Email" type="email" autoComplete="email" inputMode="email" autoFocus error={formState.errors.email?.message} {...register("email")} />
          <Button type="submit" size="full" loading={formState.isSubmitting}>Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}
