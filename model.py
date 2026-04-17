import torch
import torch.nn as nn

class FinalModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv1d(28,32,3,padding=1),
            nn.ReLU(),
            nn.Conv1d(32,32,3,padding=1),
            nn.ReLU(),
            nn.Conv1d(32,16,3,padding=1),
            nn.ReLU()
        )
        self.gru = nn.GRU(16,16,batch_first=True)
        self.decoder = nn.Sequential(
            nn.Conv1d(16,32,3,padding=1),
            nn.ReLU(),
            nn.Conv1d(32,28,3,padding=1)
        )

    def forward(self,x):
        z = self.encoder(x)
        z = z.permute(0,2,1)
        z,_ = self.gru(z)
        z = z.permute(0,2,1)
        out = self.decoder(z)
        return out, z