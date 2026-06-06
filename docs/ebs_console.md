Como obter índice das pastas do EBS:

Acesse a tela de download/upload no EBS, abra o console e digite o seguinte comando:
```javascript
for (let i = 0; i < FilePath.options.length; i++) {
    console.log(i + ": " + FilePath.options[i].label)
}
```