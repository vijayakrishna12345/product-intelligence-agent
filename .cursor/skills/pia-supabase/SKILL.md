---
name: pia-supabase
description: Supabase project xqatwvlvdfkaujhwxoer for Product Intelligence Agent. Use when applying migrations, inspecting tables, or debugging Postgres persistence.
---

# PIA Supabase

Project id: `xqatwvlvdfkaujhwxoer`. API: `https://xqatwvlvdfkaujhwxoer.supabase.co`. Do not create a second project.

## Schema changes

1. `list_tables` on `public` (verbose) before DDL.
2. `apply_migration` with the same SQL committed to `supabase/migrations/`.
3. `get_advisors` type `security` after DDL. Enable RLS on every new table.

Never use `execute_sql` for DDL. Sequence allocation is RPC `allocate_chat_sequence(p_chat_id uuid)`. Service-role key stays server-side.
