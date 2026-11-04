-- B.E.T.A. - clean up after the failed account deletes.
-- Run in Supabase: SQL Editor -> New query. Do step 1 first and look at the result.

-- 1) PREVIEW: which accounts have rows in the table, and how many each.
--    Carl's id was carl-78ac. Any other id you recognise as a deleted account is also an orphan.
select split_part(key, ':', 2) as account, count(*) as rows
from beta_kv
where key like 'u:%'
group by 1
order by 1;

-- 2) PREVIEW the rows that will be removed (should be up to six: brain, memory, model_pref, notify_prefs, push_subs, usage).
select key from beta_kv where starts_with(key, 'u:carl-78ac:');

-- 3) DELETE them.
delete from beta_kv where starts_with(key, 'u:carl-78ac:');

-- 4) CHECK: this should now return no rows.
select key from beta_kv where starts_with(key, 'u:carl-78ac:');

-- Optional, only if step 1 showed other deleted accounts: copy the delete in step 3 and replace carl-78ac with that id.
-- Do NOT delete rows whose account id belongs to a live account, or the owner's own rows.
