/**
 * A tiny key-value store on IndexedDB, for recordings waiting to upload. IndexedDB keeps
 * Blobs, survives a closed browser, and is per device: a recording is safe here from the
 * moment Stop is tapped until the server has it.
 */

const DB = "memoir";
const STORE = "uploads";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function run<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await open();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = work(tx.objectStore(STORE));
    tx.oncomplete = () => {
      db.close();
      resolve(request.result);
    };
    tx.onerror = () => reject(tx.error);
  });
}

export const store = {
  get: <T>(key: string) => run<T | undefined>("readonly", (s) => s.get(key)),
  put: (key: string, value: unknown) =>
    run("readwrite", (s) => s.put(value, key)),
  remove: (key: string) => run("readwrite", (s) => s.delete(key)),
  keys: () => run<IDBValidKey[]>("readonly", (s) => s.getAllKeys()),
};
