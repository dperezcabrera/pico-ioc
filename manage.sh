#!/usr/bin/env bash
set -euo pipefail

CMD=make
FILE=pico.txt
RELEASE_PROMPT=release_prompt.txt
context() {
  echo -e "te voy a facilitar un proyecto, para que hagas lo que te pido al final, siempre devuelve ficheros completos (o funciones completas con la clase arriba para que este bien tabulada) en bloque de codigo sin comentarios dentro, si hay textos en el codigo: ponlos siempre en ingles, no devuelvas diffs\n\n" > $FILE
  echo -e "========================================\n" >> $FILE   
  tree>>$FILE
  echo -e "========================================\n" >> $FILE 
  gettext3.sh src docs Dockerfile mkdocs.yml .github requirements.txt >>$FILE
}

context_test() {
  context
  echo -e "========================================\n" >> $FILE 
  gettext3.sh tests/test_resolution_graph.py >>$FILE
  echo -e "\n========================================\n" >> $FILE 
  echo "$CMD" >> $FILE 
  
  tests 2>>$FILE 
}

context_test_exec() {
  context_test
  echo -e "\n========================================\n" >> $FILE 
  echo "$CMD" >> $FILE 
  
  tests 2>>$FILE 
}

context_doc() {
  #context_test
  #echo -e "\n========================================\n" >> $FILE 
  gettext3.sh src docs README.md CHANGELOG.md>$FILE
}

context_release() {
  version="v2.0.3"
  echo -e "Teniendo en cuenta:\n" >$RELEASE_PROMPT
  gettext3.sh CHANGELOG.md README.md >>$RELEASE_PROMPT
  echo -e "\n========================================\n" >> $RELEASE_PROMPT 
  echo -e "para este cambio:\n" >>$RELEASE_PROMPT
  git diff --cached >>$RELEASE_PROMPT
  echo -e "asume que no hace dalta git add, pasame el:" >>$RELEASE_PROMPT
  echo -e " CHANGELOG.md completo en ingles para ${version} en un bloque en markdown" >>$RELEASE_PROMPT
  echo -e "- el commit en una linea en ingles,  con el comando completo solo para ejecutar el commit con el mensaje" >>$RELEASE_PROMPT
  echo -e "- el tag ${version} con mensaje de una linea en ingles, con el comando git completo solo para ejecutar y subir al repo" >>$RELEASE_PROMPT
  echo -e "- y una descripcion de la release en ingles para github en un bloque markdown para copiar y pegar" >>$RELEASE_PROMPT
}

tests() {
  $CMD 
}

case "${1:-}" in
  tests) tests ;;
  context) context ;;
  context_test) context_test ;;
  context_doc) context_doc ;;
  context_release) context_release ;;
  context_test_exec) context_test_exec ;;
  *) echo "usage: $0 {context|context_test|context_test_exec|context_doc|context_release|tests}"; exit 1;;
esac
